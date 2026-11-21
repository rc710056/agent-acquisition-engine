from urllib.parse import urljoin

import httpx

from apps.api.app.security.ssrf import SSRFValidator


async def send_with_safe_redirects(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    max_redirects: int = 10
) -> httpx.Response:
    current_url = url
    for _ in range(max_redirects + 1):
        is_safe, error = SSRFValidator.validate_url(current_url)
        if not is_safe:
            raise ValueError(f"Request blocked by SSRF policy: {error}")

        request = client.build_request(method, current_url, headers=headers)
        response = await client.send(request, stream=True, follow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response

        location = response.headers.get("location")
        await response.aclose()
        if not location:
            raise RuntimeError("HTTP redirect response did not include a Location header.")
        current_url = urljoin(current_url, location)

    raise RuntimeError(f"Request exceeded the maximum of {max_redirects} redirects.")
