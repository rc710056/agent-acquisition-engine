import asyncio
import os
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional, Callable, Awaitable, Dict, Any, List
import httpx
from apps.api.app.security.ssrf import SSRFValidator
from providers.direct_http.safe_http import send_with_safe_redirects

logger = logging.getLogger("aae.chunked_downloader")


class RangeDownloadError(RuntimeError):
    pass

class ChunkedDownloader:
    """
    High-concurrency chunked HTTP range downloader inspired by FileDownloader.
    Splits large files across multiple concurrent HTTP Range requests,
    writes into pre-allocated file slices, and supports progress tracking.
    """

    def __init__(self, concurrency: int = 4, chunk_buffer_size: int = 65536):
        self.concurrency = max(1, min(concurrency, 16))
        self.chunk_buffer_size = chunk_buffer_size

    async def probe_range_support(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        max_size_bytes: int = 524_288_000
    ) -> tuple[bool, Optional[int]]:
        """
        Probes the server to check if Accept-Ranges: bytes is supported
        and returns (supports_ranges, total_bytes).
        """
        req_headers = dict(headers or {})
        req_headers["User-Agent"] = req_headers.get("User-Agent", "AgentAcquisitionEngine/1.0")
        req_headers["Accept-Encoding"] = "identity"
        req_headers["Range"] = "bytes=0-0"

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
                response = await send_with_safe_redirects(client, "GET", url, req_headers)
                try:
                    if response.status_code != 206:
                        return False, None
                    content_range = response.headers.get("content-range", "")
                    match = re.fullmatch(r"bytes 0-0/(\d+)", content_range.strip(), re.IGNORECASE)
                    if not match:
                        return False, None
                    total = int(match.group(1))
                    if total <= 0 or total > max_size_bytes:
                        return True, total
                    received = 0
                    async for chunk in response.aiter_bytes(chunk_size=1):
                        received += len(chunk)
                        if received > 1:
                            return False, None
                    return received == 1, total
                finally:
                    await response.aclose()
        except httpx.HTTPError as e:
            logger.warning("Unable to probe range support; using a bounded sequential stream: %s", e)
            return False, None

        return False, None

    async def download(
        self,
        url: str,
        destination_path: Path,
        total_bytes: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], Awaitable[None]]] = None,
        timeout_seconds: int = 300,
        max_size_bytes: int = 524_288_000
    ) -> Dict[str, Any]:
        """
        Executes a high-speed chunked download if range requests are supported and file > 4MB;
        otherwise falls back to a single sequential stream.
        """
        is_safe, error = SSRFValidator.validate_url(url)
        if not is_safe:
            raise ValueError(f"Acquisition blocked by security policy: {error}")

        req_headers = dict(headers or {})
        req_headers["User-Agent"] = req_headers.get("User-Agent", "AgentAcquisitionEngine/1.0")

        # Determine range capability
        supports_ranges, probed_total = await self.probe_range_support(
            url, req_headers, max_size_bytes=max_size_bytes
        )
        file_size = total_bytes or probed_total

        destination_path.parent.mkdir(parents=True, exist_ok=True)

        # Use chunked range download only if ranges supported and file >= 4MB
        min_chunked_size = 4 * 1024 * 1024
        if supports_ranges and file_size and file_size >= min_chunked_size:
            if file_size > max_size_bytes:
                raise ValueError(f"Resource size ({file_size} bytes) exceeds maximum limit ({max_size_bytes} bytes)")

            try:
                async with asyncio.timeout(timeout_seconds):
                    return await self._download_concurrent_chunks(
                        url=url,
                        destination_path=destination_path,
                        total_bytes=file_size,
                        headers=req_headers,
                        progress_callback=progress_callback,
                        timeout_seconds=timeout_seconds
                    )
            except (RangeDownloadError, httpx.HTTPError, TimeoutError) as e:
                logger.warning("Range download failed; retrying as a bounded sequential stream: %s", e)
                destination_path.unlink(missing_ok=True)

        # Fallback: Sequential single-stream download
        async with asyncio.timeout(timeout_seconds):
            return await self._download_sequential(
                url=url,
                destination_path=destination_path,
                headers=req_headers,
                progress_callback=progress_callback,
                timeout_seconds=timeout_seconds,
                max_size_bytes=max_size_bytes
            )

    async def _download_concurrent_chunks(
        self,
        url: str,
        destination_path: Path,
        total_bytes: int,
        headers: Dict[str, str],
        progress_callback: Optional[Callable[[int, Optional[int]], Awaitable[None]]],
        timeout_seconds: int
    ) -> Dict[str, Any]:
        """
        Splits file into concurrent byte ranges, writing each chunk in parallel.
        """
        chunk_count = min(self.concurrency, total_bytes)
        chunk_size = total_bytes // chunk_count
        ranges: List[tuple[int, int]] = []
        for i in range(chunk_count):
            start = i * chunk_size
            end = total_bytes - 1 if i == chunk_count - 1 else (start + chunk_size - 1)
            ranges.append((start, end))

        # Pre-allocate sparse file
        with open(destination_path, "wb") as f:
            f.seek(total_bytes - 1)
            f.write(b"\0")

        progress_lock = asyncio.Lock()
        transferred_bytes = 0

        async def fetch_range(start: int, end: int):
            nonlocal transferred_bytes
            r_headers = dict(headers)
            r_headers["Range"] = f"bytes={start}-{end}"

            async with httpx.AsyncClient(
                timeout=float(timeout_seconds),
                follow_redirects=False,
                trust_env=False
            ) as client:
                response = await send_with_safe_redirects(client, "GET", url, r_headers)
                try:
                    expected_range = f"bytes {start}-{end}/{total_bytes}"
                    if response.status_code != 206 or response.headers.get("content-range", "").lower() != expected_range:
                        raise RangeDownloadError(
                            f"Server did not return the requested byte range {expected_range}."
                        )

                    current_pos = start
                    async for chunk in response.aiter_bytes(chunk_size=self.chunk_buffer_size):
                        if not chunk:
                            continue
                        chunk_len = len(chunk)
                        if current_pos + chunk_len > end + 1:
                            raise RangeDownloadError("Range response exceeded its requested byte interval.")
                        with open(destination_path, "r+b") as out_f:
                            out_f.seek(current_pos)
                            out_f.write(chunk)

                        current_pos += chunk_len
                        async with progress_lock:
                            transferred_bytes += chunk_len
                            if transferred_bytes > total_bytes:
                                raise RangeDownloadError("Range responses exceeded the declared file size.")
                            if progress_callback:
                                await progress_callback(transferred_bytes, total_bytes)

                    if current_pos != end + 1:
                        raise RangeDownloadError("Range response ended before the requested interval was complete.")
                finally:
                    await response.aclose()

        results = await asyncio.gather(
            *(fetch_range(start, end) for start, end in ranges),
            return_exceptions=True
        )
        errors = [result for result in results if isinstance(result, BaseException)]
        if errors:
            raise errors[0]

        # Verify integrity and calculate SHA-256
        sha256 = hashlib.sha256()
        with open(destination_path, "rb") as f:
            while chunk := f.read(131072):
                sha256.update(chunk)

        final_size = os.path.getsize(destination_path)
        if final_size != total_bytes or transferred_bytes != total_bytes:
            raise RangeDownloadError("Range responses did not produce the declared file size.")
        return {
            "bytes_downloaded": final_size,
            "sha256": sha256.hexdigest(),
            "is_chunked": True,
            "chunks_count": chunk_count
        }

    async def _download_sequential(
        self,
        url: str,
        destination_path: Path,
        headers: Dict[str, str],
        progress_callback: Optional[Callable[[int, Optional[int]], Awaitable[None]]],
        timeout_seconds: int,
        max_size_bytes: int
    ) -> Dict[str, Any]:
        """
        Standard sequential streaming download fallback.
        """
        sha256 = hashlib.sha256()
        transferred = 0
        total: Optional[int] = None

        request_headers = dict(headers)
        request_headers["Accept-Encoding"] = "identity"
        async with httpx.AsyncClient(
            timeout=float(timeout_seconds),
            follow_redirects=False,
            trust_env=False
        ) as client:
            response = await send_with_safe_redirects(client, "GET", url, request_headers)
            try:
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP request failed with status {response.status_code}")

                cl = response.headers.get("content-length")
                if cl and cl.isdigit():
                    total = int(cl)
                    if total > max_size_bytes:
                        raise ValueError(f"Resource size ({total} bytes) exceeds maximum limit ({max_size_bytes} bytes)")

                with open(destination_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=self.chunk_buffer_size):
                        if not chunk:
                            continue
                        transferred += len(chunk)
                        if transferred > max_size_bytes:
                            raise ValueError(f"File exceeded maximum limit of {max_size_bytes} bytes")
                        sha256.update(chunk)
                        f.write(chunk)
                        if progress_callback:
                            await progress_callback(transferred, total)
            finally:
                await response.aclose()

        return {
            "bytes_downloaded": transferred,
            "sha256": sha256.hexdigest(),
            "is_chunked": False,
            "chunks_count": 1
        }
