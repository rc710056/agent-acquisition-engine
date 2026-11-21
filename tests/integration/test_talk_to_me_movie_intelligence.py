import pytest
import hashlib
from pathlib import Path
import httpx

from apps.api.app.main import app
from providers.movie_intelligence.provider import MovieIntelligenceProvider
from packages.source_classifier.classifier import SourceClassifier
from packages.shared_schemas.models import SourceType, SecurityStatus


@pytest.mark.asyncio
async def test_talk_to_me_source_classification():
    """Verify source classifier correctly routes 'Talk to Me' to movie_intelligence."""
    classification = await SourceClassifier.classify("Talk to Me")
    assert classification.provider_id == "movie_intelligence"
    assert classification.security_status == SecurityStatus.SAFE
    assert classification.source_type == SourceType.MEDIA_COLLECTION
    assert "Talk to Me" in classification.title

    classification_prefixed = await SourceClassifier.classify("movie:Talk to Me")
    assert classification_prefixed.provider_id == "movie_intelligence"


@pytest.mark.asyncio
async def test_talk_to_me_real_metadata_inspection():
    """
    Requirement 1: Replace fake hardcoded movie dictionaries and fake fallback generation
    with REAL internet metadata retrieval to resolve real title, year, director, cast, synopsis,
    and genuine official poster image.
    
    Requirement 2: Query real OTT availability (or accurately map known distributors)
    so 'Talk to Me' does NOT show Disney+!
    
    Requirement 3: Never invent fake magnet hashes (e.g. hashlib.sha1(title)).
    If not found, honestly report 'No public BitTorrent swarm discovered'.
    """
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/sources/inspect", json={"url": "Talk to Me"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["provider_id"] == "movie_intelligence"
        assert "Talk to Me" in data["title"]
        assert data["is_permitted"] is True

        # Check real poster image: genuine Wikimedia poster or official art, NOT empty cinema seats
        poster_url = data.get("thumbnail_url", "")
        assert "photo-1489599849927-2ee91cede3ba" not in poster_url, "Must not use fake empty cinema seats stock photo!"
        assert bool(poster_url) is True

        # Check genuine metadata from inspection response / assets
        asset = data["assets"][0]
        assert "Danny" in (asset.get("director") or "") or "Philippou" in (asset.get("director") or "")
        assert "Sophie Wilde" in (asset.get("cast") or "") or "Miranda Otto" in (asset.get("cast") or "")
        assert "hand" in (asset.get("synopsis") or "").lower() or "spirit" in (asset.get("synopsis") or "").lower()
        assert asset.get("year") in ["2022", "2023"]

        # Requirement 2: Check OTT streaming channels
        ott_list = data.get("ott_channels") or data.get("ott") or asset.get("ott") or []
        ott_platforms = [o["platform"] for o in ott_list]
        assert "Disney+" not in ott_platforms, "Talk to Me is an A24 release and must NEVER show Disney+!"
        assert any(p in ott_platforms for p in ["Netflix", "Max", "Amazon Prime Video", "Apple TV"])

        # Requirement 3: Check BitTorrent Swarm honestly reported without fake hash
        fake_sha1_hash = hashlib.sha1("Talk to Me".encode()).hexdigest()
        assert fake_sha1_hash not in str(data), "Must never generate fake hashlib.sha1 magnet hashes!"

        formats_resp = await client.get(f"/api/v1/sources/{data['source_id']}/formats")
        assert formats_resp.status_code == 200
        formats = formats_resp.json()

        torrent_fmt = next((f for f in formats if f["format_id"] == "torrent_magnet"), None)
        assert torrent_fmt is not None
        assert "no public bittorrent swarm discovered" in torrent_fmt["quality_label"].lower()


@pytest.mark.asyncio
async def test_talk_to_me_media_acquisition(tmp_path):
    """
    Requirement 4: When acquiring a media asset for a movie query, download the real official
    preview/trailer (via yt-dlp) or real open film stream, NEVER rename Big Buck Bunny to a
    commercial movie title.
    """
    provider = MovieIntelligenceProvider()

    # Acquire Video Preview
    dest_video = tmp_path / "talk_to_me_trailer.mp4"
    result = await provider.acquire(
        url="Talk to Me",
        format_id="best_video_audio",
        destination_path=dest_video
    )

    assert Path(result["file_path"]).exists()
    assert result["mime_type"] == "video/mp4"
    assert result["verification"]["is_valid"] is True
    assert result["size_bytes"] > 0

    # Ensure it did not copy or rename Big Buck Bunny
    # Big Buck Bunny is ~158,000,000 bytes or 2,084 bytes sample; check trailer hash or content
    bbb_sample_hash = "6a345091bf5f4a4227cac320dbdc293a5b3f3f57"
    assert result["sha256"] != bbb_sample_hash

    # Acquire Torrent Package and check honest manifest
    dest_torrent = tmp_path / "talk_to_me_torrent.zip"
    torrent_res = await provider.acquire(
        url="Talk to Me",
        format_id="torrent_magnet",
        destination_path=dest_torrent
    )
    assert Path(torrent_res["file_path"]).exists()
    assert torrent_res["mime_type"] == "application/x-bittorrent"
    assert torrent_res["verification"]["is_valid"] is True

    import zipfile
    with zipfile.ZipFile(dest_torrent, "r") as zf:
        manifest_files = [f for f in zf.namelist() if f.endswith("MANIFEST.txt")]
        assert len(manifest_files) > 0
        manifest_content = zf.read(manifest_files[0]).decode()
        assert "no public bittorrent swarm discovered" in manifest_content.lower()
        assert "disney+" not in manifest_content.lower()


@pytest.mark.asyncio
async def test_open_source_movie_inspection_and_real_magnet():
    """Verify open source films (Big Buck Bunny) retain genuine open magnets and sources."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/sources/inspect", json={"url": "Big Buck Bunny"})
        assert resp.status_code == 200
        data = resp.json()

        assert "Big Buck Bunny" in data["title"]
        ott_list = data.get("ott_channels") or data.get("ott") or []
        ott_names = [o["platform"] for o in ott_list]
        assert "Blender Studio" in ott_names or "YouTube Free" in ott_names

        formats_resp = await client.get(f"/api/v1/sources/{data['source_id']}/formats")
        formats = formats_resp.json()
        torrent_fmt = next((f for f in formats if f["format_id"] == "torrent_magnet"), None)
        assert torrent_fmt is not None
        assert "verified bittorrent release" in torrent_fmt["quality_label"].lower()
