import asyncio
import os
import sys
import hashlib
import subprocess
from pathlib import Path

from services.mcp_server.server import acquire_media, preview_media

async def run_live_test():
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print("=" * 60)
    print("STEP 1: PREVIEW LIVE URL")
    print("=" * 60)
    preview = await preview_media(test_url)
    print("Preview Success:", preview.get("success"))
    if not preview.get("success"):
        print("Preview Error:", preview.get("error"))
        return

    data = preview["data"]
    print("Title:", data.get("title"))
    print("Duration (s):", data.get("duration_seconds"))
    print(f"Options found ({len(data['options'])}):")
    for opt in data["options"]:
        print(f"  - [{opt.get('format_id')}] {opt.get('label')} | {opt.get('resolution')} | {opt.get('codec')} | {opt.get('estimated_size')}")

    print("\n" + "=" * 60)
    print("STEP 2: LIVE ACQUISITION (AUDIO ONLY MP3)")
    print("=" * 60)
    audio_res = await acquire_media(test_url, format_id="best_audio_mp3")
    print("Audio Result Success:", audio_res.get("success"))
    if not audio_res.get("success"):
        print("Audio Error:", audio_res.get("error"))
    else:
        adata = audio_res["data"]
        print("Delivered file:", adata.get("filename"))
        print("Size bytes:", adata.get("size_bytes"))
        print("SHA256:", adata.get("sha256"))
        print("MIME type:", adata.get("mime_type"))
        print("Download URL:", adata.get("download_url"))
        art_id = adata.get("artifact_id")
        # Check actual file on disk
        storage_dir = Path("storage/artifacts")
        matching = list(storage_dir.glob(f"*{adata.get('filename')}*"))
        if matching:
            fpath = matching[0]
            print(f"File verified on disk: {fpath.name} ({fpath.stat().st_size:,} bytes)")
            # Run ffprobe
            try:
                cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_name,sample_rate", "-of", "default=noprint_wrappers=1", str(fpath)]
                p = subprocess.run(cmd, capture_output=True, text=True)
                print("FFprobe output:\n" + p.stdout.strip())
            except Exception as e:
                print("FFprobe probe failed:", e)

    print("\n" + "=" * 60)
    print("STEP 3: LIVE ACQUISITION (COMPATIBLE VIDEO 360p)")
    print("=" * 60)
    video_res = await acquire_media(test_url, format_id="best_360p_mp4")
    print("Video Result Success:", video_res.get("success"))
    if not video_res.get("success"):
        print("Video Error:", video_res.get("error"))
    else:
        vdata = video_res["data"]
        print("Delivered file:", vdata.get("filename"))
        print("Size bytes:", vdata.get("size_bytes"))
        print("SHA256:", vdata.get("sha256"))
        print("MIME type:", vdata.get("mime_type"))
        print("Download URL:", vdata.get("download_url"))
        art_id = vdata.get("artifact_id")
        storage_dir = Path("storage/artifacts")
        matching = list(storage_dir.glob(f"*{vdata.get('filename')}*"))
        if matching:
            fpath = matching[0]
            print(f"File verified on disk: {fpath.name} ({fpath.stat().st_size:,} bytes)")
            try:
                cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_name,width,height,r_frame_rate", "-of", "default=noprint_wrappers=1", str(fpath)]
                p = subprocess.run(cmd, capture_output=True, text=True)
                print("FFprobe output:\n" + p.stdout.strip())
            except Exception as e:
                print("FFprobe probe failed:", e)

if __name__ == "__main__":
    asyncio.run(run_live_test())
