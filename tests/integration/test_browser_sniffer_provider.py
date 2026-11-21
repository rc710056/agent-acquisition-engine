import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from providers.browser_sniffer.provider import BrowserSnifferProvider
from packages.shared_schemas.models import SecurityStatus

@pytest.mark.asyncio
async def test_browser_sniffer_can_handle():
    sniffer = BrowserSnifferProvider()
    assert sniffer.can_handle("https://example.com/player.html") is True
    assert sniffer.can_handle("http://streaming-site.tv/live") is True
    assert sniffer.can_handle("ftp://example.com/file") is False

@pytest.mark.asyncio
async def test_browser_sniffer_ssrf_blocking():
    sniffer = BrowserSnifferProvider()
    insp = await sniffer.inspect("http://127.0.0.1:8000/internal-stream")
    assert insp.is_permitted is False
    assert insp.security_status == SecurityStatus.BLOCKED
    assert any("Loopback" in err or "SSRF" in err for err in insp.errors)

@pytest.mark.asyncio
async def test_browser_sniffer_stream_interception():
    sniffer = BrowserSnifferProvider()
    target_url = "https://example.com/dynamic-video-page"

    # Mock playwright page and response event
    mock_resp_hls = MagicMock()
    mock_resp_hls.url = "https://cdn.example.com/live/master.m3u8"
    mock_resp_hls.headers = {"content-type": "application/vnd.apple.mpegurl"}

    mock_page = AsyncMock()
    mock_page.title.return_value = "Interactive Player Page"

    async def fake_goto(url, wait_until, timeout):
        # Trigger on_response listener
        for handler in mock_page._response_handlers:
            await handler(mock_resp_hls)

    mock_page.goto = fake_goto
    mock_page.wait_for_timeout = AsyncMock()
    mock_page._response_handlers = []
    mock_page.on = lambda event, cb: mock_page._response_handlers.append(cb)

    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_p = AsyncMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_playwright_cm = AsyncMock()
    mock_playwright_cm.__aenter__.return_value = mock_p
    mock_playwright_cm.__aexit__.return_value = None

    with patch("providers.browser_sniffer.provider.async_playwright", return_value=mock_playwright_cm):
        insp = await sniffer.inspect(target_url)

    assert insp.is_permitted is True
    assert insp.provider_id == "browser_sniffer"
    assert len(insp.formats) >= 1
    fmt = insp.formats[0]
    assert "HLS Stream" in fmt.quality_label
    assert fmt.has_audio is True
    assert "https://cdn.example.com/live/master.m3u8" == fmt.download_url
