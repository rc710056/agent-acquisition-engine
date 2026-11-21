import pytest
from pathlib import Path
import bencode
from providers.torrent.provider import TorrentProvider
from packages.shared_schemas.models import SourceType, SecurityStatus

@pytest.mark.asyncio
async def test_torrent_provider_magnet_inspection():
    provider = TorrentProvider()
    magnet_url = "magnet:?xt=urn:btih:3b245504cf5f11bbdbe1201cea6a6bf45aee1bc0&dn=Ubuntu+22.04+LTS&tr=https%3A%2F%2Ftorrent.ubuntu.com%2Fannounce"

    assert provider.can_handle(magnet_url) is True

    inspection = await provider.inspect(magnet_url)
    assert inspection.is_permitted is True
    assert inspection.provider_id == "torrent"
    assert inspection.source_type == SourceType.MEDIA_COLLECTION
    assert "Ubuntu 22.04 LTS" in inspection.title
    assert len(inspection.formats) >= 1
    assert inspection.formats[0].format_id == "all_files"
    assert "p2p_torrent" in inspection.capabilities

@pytest.mark.asyncio
async def test_torrent_provider_magnet_ssrf_tracker_blocking():
    provider = TorrentProvider()
    # Tracker attempts SSRF against loopback internal admin
    malicious_magnet = "magnet:?xt=urn:btih:3b245504cf5f11bbdbe1201cea6a6bf45aee1bc0&dn=Malicious&tr=http%3A%2F%2F127.0.0.1%3A8000%2Fadmin"

    inspection = await provider.inspect(malicious_magnet)
    assert inspection.is_permitted is False
    assert inspection.security_status == SecurityStatus.BLOCKED
    assert any("violates SSRF policy" in err for err in inspection.errors)

@pytest.mark.asyncio
async def test_torrent_provider_torrent_file_bencode(monkeypatch):
    provider = TorrentProvider()
    torrent_url = "https://example.com/downloads/archlinux.torrent"

    torrent_meta = {
        b"announce": b"https://tracker.archlinux.org/announce",
        b"info": {
            b"name": b"archlinux-2026.iso",
            b"length": 1048576000,
            b"piece length": 524288,
            b"pieces": b"x" * 20
        }
    }
    encoded_torrent = bencode.encode(torrent_meta)

    from unittest.mock import AsyncMock, MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = encoded_torrent
    mock_resp.url = torrent_url

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_client)

    inspection = await provider.inspect(torrent_url)
    assert inspection.is_permitted is True
    assert "archlinux-2026.iso" in inspection.title
    assert inspection.estimated_size_bytes == 1048576000
    assert len(inspection.formats) >= 1

@pytest.mark.asyncio
async def test_torrent_provider_acquire(tmp_path: Path):
    provider = TorrentProvider()
    magnet_url = "magnet:?xt=urn:btih:3b245504cf5f11bbdbe1201cea6a6bf45aee1bc0&dn=TestDataset"
    dest_path = tmp_path / "test_dataset.zip"

    res = await provider.acquire(
        url=magnet_url,
        format_id="all_files",
        destination_path=dest_path
    )

    assert Path(res["destination_path"]).exists()
    assert res["mime_type"] == "application/zip"
    assert res["transferred_bytes"] > 0
    assert res["sha256"] is not None
