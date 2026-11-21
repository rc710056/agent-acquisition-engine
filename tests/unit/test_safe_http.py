from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.direct_http.safe_http import send_with_safe_redirects


@pytest.mark.asyncio
async def test_redirect_destination_is_validated_before_request():
    redirect = MagicMock()
    redirect.status_code = 302
    redirect.headers = {"location": "http://127.0.0.1/private"}
    redirect.aclose = AsyncMock()

    client = MagicMock()
    client.build_request.return_value = object()
    client.send = AsyncMock(return_value=redirect)

    with patch(
        "providers.direct_http.safe_http.SSRFValidator.validate_url",
        side_effect=[(True, None), (False, "private address")]
    ) as validate_url:
        with pytest.raises(ValueError, match="blocked by SSRF policy"):
            await send_with_safe_redirects(
                client,
                "GET",
                "https://example.com/file",
                {}
            )

    assert validate_url.call_count == 2
    assert client.send.await_count == 1
