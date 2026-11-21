import pytest
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from providers.direct_http.chunked_downloader import ChunkedDownloader

@pytest.mark.asyncio
async def test_chunked_downloader_sequential_fallback(tmp_path: Path):
    downloader = ChunkedDownloader(concurrency=4)
    dest_path = tmp_path / "test_seq.bin"
    test_content = b"Sequential fallback test content" * 100

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-length": str(len(test_content))}
    async def aiter_bytes(chunk_size=65536):
        yield test_content
    mock_resp.aiter_bytes = aiter_bytes

    mock_stream = AsyncMock()
    mock_stream.__aenter__.return_value = mock_resp
    mock_stream.__aexit__.return_value = None

    with patch("httpx.AsyncClient.stream", return_value=mock_stream):
        res = await downloader.download(
            url="https://example.com/file.bin",
            destination_path=dest_path,
            total_bytes=len(test_content)
        )

    assert dest_path.exists()
    assert dest_path.read_bytes() == test_content
    assert res["bytes_downloaded"] == len(test_content)
    assert res["is_chunked"] is False

@pytest.mark.asyncio
async def test_chunked_downloader_concurrent_ranges(tmp_path: Path):
    downloader = ChunkedDownloader(concurrency=2)
    dest_path = tmp_path / "test_chunked.bin"
    # Create 5MB test buffer
    chunk1 = b"A" * (256 * 1024)
    chunk2 = b"B" * (256 * 1024)
    total_len = 5 * 1024 * 1024

    with patch.object(downloader, "probe_range_support", return_value=(True, total_len)):
        with patch.object(downloader, "_download_concurrent_chunks", return_value={
            "bytes_downloaded": total_len,
            "sha256": "fakehash",
            "is_chunked": True,
            "chunks_count": 2
        }) as mock_chunks:
            res = await downloader.download(
                url="https://example.com/largefile.bin",
                destination_path=dest_path,
                total_bytes=total_len
            )
            assert mock_chunks.called
            assert res["is_chunked"] is True
            assert res["chunks_count"] == 2
