import pytest
from pathlib import Path
import bencode
from providers.torrent.provider import (
    TorrentProvider,
    TorrentTransportUnavailableError,
    is_tracker_trusted
)
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
    assert "piece_hash_verification" in inspection.capabilities
    assert inspection.metadata.get("dht_pex_disabled") is True
    assert inspection.metadata.get("seed_ratio") == 0.0


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
async def test_torrent_provider_untrusted_tracker_rejection():
    provider = TorrentProvider()
    # Piracy / untrusted tracker
    untrusted_magnet = "magnet:?xt=urn:btih:3b245504cf5f11bbdbe1201cea6a6bf45aee1bc0&dn=PiratedMedia&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"

    inspection = await provider.inspect(untrusted_magnet)
    assert inspection.is_permitted is False
    assert inspection.security_status in (SecurityStatus.REQUIRES_REVIEW, SecurityStatus.BLOCKED)
    assert any("Untrusted tracker host detected" in err for err in inspection.errors)


@pytest.mark.asyncio
async def test_torrent_provider_torrent_file_bencode(monkeypatch):
    provider = TorrentProvider()
    torrent_url = "https://example.com/downloads/archlinux.torrent"

    torrent_meta = {
        b"announce": b"https://torrent.ubuntu.com/announce",
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
async def test_torrent_provider_fail_closed_on_unavailable_transport(tmp_path: Path):
    """
    Verifies that when a torrent transport cannot connect to peers or resolve metadata,
    it strictly FAILS CLOSED by raising TorrentTransportUnavailableError.
    Under no circumstances are mock bytes or fabricated manifests written to disk.
    """
    provider = TorrentProvider()
    # Non-existent magnet with trusted tracker format but zero peers
    dead_magnet = "magnet:?xt=urn:btih:0000000000000000000000000000000000000001&dn=NonExistent&tr=https%3A%2F%2Ftorrent.ubuntu.com%2Fannounce"
    dest_path = tmp_path / "never_created.bin"

    with pytest.raises(TorrentTransportUnavailableError) as exc_info:
        await provider.acquire(
            url=dead_magnet,
            format_id="all_files",
            destination_path=dest_path,
            timeout_seconds=2
        )

    assert "TORRENT_TRANSPORT_UNAVAILABLE" in str(exc_info.value)
    assert exc_info.value.error_code == "TORRENT_TRANSPORT_UNAVAILABLE"
    assert not dest_path.exists(), "No fabricated or spoofed file should exist on disk."


@pytest.mark.asyncio
async def test_torrent_provider_real_selective_download(tmp_path: Path):
    """
    Verifies genuine BitTorrent download with piece-hash verification using
    the official archive.org Elephants Dream torrent and selective file downloading.
    """
    provider = TorrentProvider()
    torrent_url = "https://archive.org/download/ElephantsDream/ElephantsDream_archive.torrent"

    # 1. Inspect genuine torrent
    inspection = await provider.inspect(torrent_url)
    assert inspection.is_permitted is True
    assert "ElephantsDream" in inspection.title
    assert len(inspection.formats) > 1

    # Locate the mp3 soundtrack file format_id
    target_format = None
    for fmt in inspection.formats:
        if "ED-CM-5.1-DVD-C.mp3" in (fmt.quality_label or ""):
            target_format = fmt
            break

    assert target_format is not None
    assert target_format.estimated_size_bytes == 8280576

    # 2. Acquire target file selectively
    dest_path = tmp_path / "ElephantsDream_soundtrack.mp3"
    result = await provider.acquire(
        url=torrent_url,
        format_id=target_format.format_id,
        destination_path=dest_path,
        timeout_seconds=60
    )

    assert dest_path.exists()
    assert result["is_verified"] is True
    assert result["piece_hash_verified"] is True
    assert result["provenance"] == "libtorrent_verified_pieces"
    assert result["seed_ratio"] == 0.0
    assert result["dht_pex_disabled"] is True
    assert result["transferred_bytes"] == 8280576
    assert result["sha256"] == "eea7d09c0be649629d71948ebd44f53b050f7c0af3c4d0b5625ca96073c285f8"
