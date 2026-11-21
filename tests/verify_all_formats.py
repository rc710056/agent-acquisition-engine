import asyncio
import httpx

async def test_all():
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
        targets = [
            ("Iron Man", "best_video_audio", True),
            ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", "original", False),
            ("magnet:?xt=urn:btih:3b245504fb5f4a4227cac320dbdc293a5b3f3f57&dn=Big+Buck+Bunny+1080p&tr=https%3A%2F%2Ftorrent.ubuntu.com%3A443%2Fannounce", "all_files", False)
        ]
        for url, fmt, auto_app in targets:
            print(f"=== Testing {url[:35]} ===")
            r_insp = await client.post("/api/v1/sources/inspect", json={"url": url})
            assert r_insp.status_code == 200, f"Inspect failed: {r_insp.text}"
            insp = r_insp.json()
            source_id = insp["source_id"]
            print(f"Inspected: {insp.get('title')}, source_id={source_id}")

            r_job = await client.post("/api/v1/acquisitions/jobs", json={
                "source_id": source_id,
                "format_id": fmt,
                "auto_approve": auto_app
            })
            assert r_job.status_code == 201, f"Create job failed: {r_job.text}"
            job = r_job.json()
            job_id = job["job_id"]
            print(f"Job created: {job_id}")

            # Poll for completion
            for _ in range(40):
                await asyncio.sleep(0.5)
                r_status = await client.get(f"/api/v1/acquisitions/jobs/{job_id}")
                st = r_status.json()
                if st["state"] in ("completed", "failed"):
                    print(f"Job ended in state: {st['state']}, progress: {st['progress_percent']}%, artifact: {st.get('artifact_id')}, err: {st.get('error_message')}")
                    assert st["state"] == "completed", f"Job failed: {st.get('error_message')}"
                    break

        print("=== ALL 3 FORMATS COMPLETED AND STORED SUCCESSFULLY! ===")

if __name__ == "__main__":
    asyncio.run(test_all())
