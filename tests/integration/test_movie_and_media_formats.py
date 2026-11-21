import pytest
import httpx
from pathlib import Path

from apps.api.app.main import app
from providers.registry import provider_registry
from providers.movie_intelligence.provider import MovieIntelligenceProvider

@pytest.mark.asyncio
async def test_movie_query_inspection_and_ott_discovery():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Inspect movie by plain title
        resp = await client.post("/api/v1/sources/inspect", json={"url": "Iron Man"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_permitted"] is True
        assert data["provider_id"] == "movie_intelligence"
        assert "Iron Man" in data["title"]
        assert bool(data["source_id"]) is True

        # Check formats returned
        formats_resp = await client.get(f"/api/v1/sources/{data['source_id']}/formats")
        assert formats_resp.status_code == 200
        formats = formats_resp.json()

        format_ids = [f["format_id"] for f in formats]
        assert "best_video_audio" in format_ids
        assert "best_audio_mp3" in format_ids
        assert "torrent_magnet" in format_ids
        assert "4k_hdr_bluray" in format_ids

@pytest.mark.asyncio
async def test_movie_format_acquisitions_video_and_mp3(tmp_path):
    provider = MovieIntelligenceProvider()

    # 1. Acquire Synchronized MP4 Video
    video_dest = tmp_path / "iron_man_test"
    video_res = await provider.acquire(
        url="Iron Man",
        format_id="best_video_audio",
        destination_path=video_dest
    )
    assert Path(video_res["file_path"]).exists()
    assert video_res["mime_type"] == "video/mp4"
    assert video_res["verification"]["is_valid"] is True
    assert video_res["verification"]["size_bytes"] > 0

    # 2. Acquire MP3 Soundtrack Audio
    audio_dest = tmp_path / "iron_man_soundtrack_test"
    audio_res = await provider.acquire(
        url="Iron Man",
        format_id="best_audio_mp3",
        destination_path=audio_dest
    )
    assert Path(audio_res["file_path"]).exists()
    assert audio_res["mime_type"] == "audio/mp3"
    assert audio_res["verification"]["is_valid"] is True
    assert audio_res["verification"]["size_bytes"] > 0

    # 3. Acquire BitTorrent Package
    torrent_dest = tmp_path / "iron_man_torrent_test"
    torrent_res = await provider.acquire(
        url="Iron Man",
        format_id="torrent_magnet",
        destination_path=torrent_dest
    )
    assert Path(torrent_res["file_path"]).exists()
    assert torrent_res["mime_type"] == "application/x-bittorrent"
    assert torrent_res["verification"]["is_valid"] is True
    assert torrent_res["verification"]["size_bytes"] > 0

@pytest.mark.asyncio
async def test_magnet_link_inspection_and_formats():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        magnet_url = "magnet:?xt=urn:btih:3b245504cf5f11bbdbe1201cea6a6bf45aee1bc0&dn=Ubuntu+22.04+LTS&tr=https%3A%2F%2Ftorrent.ubuntu.com%2Fannounce"
        resp = await client.post("/api/v1/sources/inspect", json={"url": magnet_url})
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_permitted"] is True
        assert data["provider_id"] == "torrent"
        assert "Ubuntu 22.04 LTS" in data["title"]
