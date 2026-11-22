import pytest
import httpx
from packages.source_classifier.classifier import SourceClassifier
from packages.shared_schemas.models import SourceType, SourceAccessStatus, SecurityStatus
from providers.registry import provider_registry

@pytest.mark.asyncio
async def test_archive_org_routing():
    url = "https://archive.org/details/night_of_the_living_dead"
    provider = provider_registry.find_provider_for_url(url)
    assert provider is not None
    assert provider.provider_id == "internet_archive"
    assert provider.can_handle(url) is True

@pytest.mark.asyncio
async def test_torrent_url_routing(monkeypatch):
    url = "https://webtorrent.io/torrents/sintel.torrent"

    async def mock_fetch(client, current_url, headers):
        return 200, {"content-type": "application/x-bittorrent", "content-length": "1234"}, current_url, [current_url], ""

    monkeypatch.setattr(SourceClassifier, "_fetch_head_or_get", mock_fetch)

    res = await SourceClassifier.classify(url)
    assert res.provider_id == "torrent"
    assert res.source_type == SourceType.MEDIA_COLLECTION

@pytest.mark.asyncio
async def test_source_blocked_status_codes(monkeypatch):
    blocked_codes = [403, 429, 503]
    for code in blocked_codes:
        async def mock_fetch(client, current_url, headers, c=code):
            return c, {}, current_url, [current_url], ""

        monkeypatch.setattr(SourceClassifier, "_fetch_head_or_get", mock_fetch)

        res = await SourceClassifier.classify("https://en.wikipedia.org/wiki/Special:Export")
        assert res.source_type == SourceType.SOURCE_BLOCKED
        assert res.source_access_status == SourceAccessStatus.BLOCKED
        assert res.inspection_status == "blocked"

@pytest.mark.asyncio
async def test_anti_bot_challenge_detection(monkeypatch):
    async def mock_fetch(client, current_url, headers):
        body = "<html><title>Just a moment...</title><body>Checking your browser before accessing cloudflare...</body></html>"
        return 200, {"cf-mitigated": "challenge"}, current_url, [current_url], body

    monkeypatch.setattr(SourceClassifier, "_fetch_head_or_get", mock_fetch)

    res = await SourceClassifier.classify("https://example.com/data")
    assert res.source_type == SourceType.SOURCE_BLOCKED
    assert res.source_access_status == SourceAccessStatus.BLOCKED
    assert res.inspection_status == "blocked"

def test_descriptive_bot_user_agent():
    from providers.direct_http.provider import DirectHTTPProvider
    from providers.internet_archive.provider import BOT_USER_AGENT

    expected_ua = "agent-acquisition-engine/0.2.0 (+https://github.com/rc710056/agent-acquisition-engine; bot)"
    assert BOT_USER_AGENT == expected_ua
