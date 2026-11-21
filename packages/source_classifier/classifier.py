import re
import os
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, unquote
import httpx

from packages.shared_schemas.models import (
    SourceType,
    SecurityStatus,
    AcquisitionPermission,
    SourceAccessStatus
)
from apps.api.app.security.ssrf import SSRFValidator

KNOWN_SHORTENERS = {
    "pin.it", "t.co", "bit.ly", "tinyurl.com", "goo.gl", "ow.ly",
    "buff.ly", "is.gd", "cutt.ly", "rb.gy", "youtu.be"
}

KNOWN_PLATFORM_DOMAINS = {
    "pinterest.com": "pinterest",
    "pin.it": "pinterest",
    "youtube.com": "permitted_media",
    "youtu.be": "permitted_media",
    "vimeo.com": "permitted_media",
    "reddit.com": "permitted_media",
    "v.redd.it": "permitted_media",
    "imgur.com": "gallery_dl",
    "deviantart.com": "gallery_dl",
    "artstation.com": "gallery_dl",
    "flickr.com": "gallery_dl",
    "instagram.com": "unsupported_restricted",
    "tiktok.com": "unsupported_restricted",
    "twitter.com": "unsupported_restricted",
    "x.com": "unsupported_restricted",
}

DIRECT_FILE_EXTENSIONS = {
    # Documents
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp",
    # Images
    "png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "tiff", "ico",
    # Audio
    "mp3", "wav", "flac", "aac", "ogg", "m4a", "wma",
    # Video
    "mp4", "mkv", "webm", "avi", "mov", "flv", "m4v",
    # Archives & Packages
    "zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar", "torrent",
    # Binaries & Data
    "exe", "bin", "iso", "dmg", "deb", "rpm", "csv", "json", "parquet", "xml"
}

class ClassificationResult:
    def __init__(
        self,
        original_url: str,
        resolved_url: str,
        source_type: SourceType,
        provider_id: str,
        security_status: SecurityStatus = SecurityStatus.SAFE,
        acquisition_permission: AcquisitionPermission = AcquisitionPermission.PERMITTED,
        source_access_status: SourceAccessStatus = SourceAccessStatus.ACCESSIBLE,
        mime_type: Optional[str] = None,
        estimated_size_bytes: Optional[int] = None,
        redirect_chain: Optional[List[str]] = None,
        title: Optional[str] = None,
        extracted_media_links: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[str]] = None
    ):
        self.original_url = original_url
        self.resolved_url = resolved_url
        self.source_type = source_type
        self.provider_id = provider_id
        self.security_status = security_status
        self.acquisition_permission = acquisition_permission
        self.source_access_status = source_access_status
        self.mime_type = mime_type
        self.estimated_size_bytes = estimated_size_bytes
        self.redirect_chain = redirect_chain or []
        self.title = title
        self.extracted_media_links = extracted_media_links or []
        self.errors = errors or []

class SourceClassifier:
    """
    Intelligent source classifier that determines the true nature of a target URL.
    Distinguishes direct binary downloads from HTML landing pages, platform media,
    shortened links, and restricted/unsupported services.
    """

    @classmethod
    async def classify(
        cls,
        url: str,
        timeout_seconds: float = 12.0,
        custom_client: Optional[httpx.AsyncClient] = None
    ) -> ClassificationResult:
        url = url.strip()

        # Handle BitTorrent magnet URIs directly
        if url.startswith("magnet:?"):
            is_safe, ssrf_err = SSRFValidator.validate_url(url)
            if not is_safe:
                return ClassificationResult(
                    original_url=url,
                    resolved_url=url,
                    source_type=SourceType.UNSUPPORTED_SOURCE,
                    provider_id="unsupported",
                    security_status=SecurityStatus.BLOCKED,
                    acquisition_permission=AcquisitionPermission.RESTRICTED,
                    source_access_status=SourceAccessStatus.BLOCKED,
                    errors=[f"Security Policy Violation: {ssrf_err}"]
                )
            return ClassificationResult(
                original_url=url,
                resolved_url=url,
                source_type=SourceType.MEDIA_COLLECTION,
                provider_id="torrent",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.PERMITTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                mime_type="application/x-bittorrent",
                title="BitTorrent Magnet Link"
            )

        parsed = urlparse(url)

        # 1. Syntax & Scheme validation
        if not parsed.scheme or not parsed.netloc:
            lowered = url.lower().strip()
            # If explicitly prefixed with movie:/search:, or matches cinematic titles or multi-word natural queries
            is_movie_query = (
                lowered.startswith("movie:") or
                lowered.startswith("search:") or
                any(m in lowered for m in ("iron man", "big buck bunny", "interstellar", "elephants dream", "avatar")) or
                (" " in lowered and not lowered.startswith("http"))
            )
            if is_movie_query and not any(lowered.startswith(prefix) for prefix in ("file:", "javascript:", "data:", "ftp:", "ldap:")):
                clean_title = url.replace("movie:", "").replace("search:", "").strip()
                return ClassificationResult(
                    original_url=url,
                    resolved_url=f"movie:{clean_title}",
                    source_type=SourceType.MEDIA_COLLECTION,
                    provider_id="movie_intelligence",
                    security_status=SecurityStatus.SAFE,
                    acquisition_permission=AcquisitionPermission.PERMITTED,
                    source_access_status=SourceAccessStatus.ACCESSIBLE,
                    mime_type="video/mp4",
                    title=f"Movie / Media Query: {clean_title}"
                )

            return ClassificationResult(
                original_url=url,
                resolved_url=url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.BLOCKED,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.BLOCKED,
                errors=["Invalid URL format: scheme or host is missing."]
            )

        if parsed.scheme.lower() not in {"http", "https"}:
            return ClassificationResult(
                original_url=url,
                resolved_url=url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.BLOCKED,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.BLOCKED,
                errors=[f"Unsupported protocol scheme '{parsed.scheme}'. Only HTTP, HTTPS, and magnet are permitted."]
            )

        # 2. SSRF check on initial target
        is_safe, ssrf_err = SSRFValidator.validate_url(url)
        if not is_safe:
            return ClassificationResult(
                original_url=url,
                resolved_url=url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.BLOCKED,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.BLOCKED,
                errors=[f"Security Policy Violation: {ssrf_err}"]
            )

        # 3. Follow redirects safely to find canonical/resolved URL
        redirect_chain = [url]
        current_url = url
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,video/*,audio/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

        resp_headers = {}
        status_code = 200
        response_body = ""

        try:
            if custom_client:
                client = custom_client
                res = await cls._fetch_head_or_get(client, current_url, headers)
                status_code, resp_headers, current_url, redirect_chain, response_body = res
            else:
                async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
                    res = await cls._fetch_head_or_get(client, current_url, headers)
                    status_code, resp_headers, current_url, redirect_chain, response_body = res
        except Exception as e:
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.UNKNOWN,
                source_access_status=SourceAccessStatus.UNAVAILABLE,
                redirect_chain=redirect_chain,
                errors=[f"Network resolution error: {str(e)}"]
            )

        # 4. Handle HTTP Status Codes (Auth required, Unavailable, Forbidden)
        if status_code in {401, 403}:
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.USER_AUTHORIZATION_REQUIRED,
                source_access_status=SourceAccessStatus.AUTHENTICATION_REQUIRED,
                redirect_chain=redirect_chain,
                errors=[f"Source returned HTTP {status_code}: Authentication or permission required."]
            )

        if status_code >= 400:
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.UNKNOWN,
                source_access_status=SourceAccessStatus.UNAVAILABLE,
                redirect_chain=redirect_chain,
                errors=[f"Source returned HTTP error {status_code}."]
            )

        # 5. Analyze Content-Type and URL features
        content_type_raw = resp_headers.get("content-type", "application/octet-stream")
        mime_type = content_type_raw.split(";")[0].strip().lower()
        cl = resp_headers.get("content-length")
        content_length = int(cl) if (cl and cl.isdigit()) else None

        resolved_domain = cls._extract_root_domain(current_url)

        # Check known platform domains first
        platform_id = cls._match_platform_domain(resolved_domain)
        if platform_id == "pinterest":
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.PLATFORM_MEDIA_PAGE,
                provider_id="pinterest",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.PERMITTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                mime_type=mime_type,
                estimated_size_bytes=None,
                redirect_chain=redirect_chain
            )

        if platform_id == "permitted_media":
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.PLATFORM_MEDIA_PAGE,
                provider_id="permitted_media",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.PERMITTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                mime_type=mime_type,
                estimated_size_bytes=None,
                redirect_chain=redirect_chain
            )

        if platform_id == "gallery_dl":
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.MEDIA_COLLECTION,
                provider_id="gallery_dl",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.PERMITTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                mime_type="application/zip",
                estimated_size_bytes=None,
                redirect_chain=redirect_chain
            )

        if platform_id == "unsupported_restricted":
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.BLOCKED,
                mime_type=mime_type,
                redirect_chain=redirect_chain,
                errors=[f"Platform '{resolved_domain}' is restricted by access controls and platform policy."]
            )

        # 6. Check for DIRECT_FILE
        # CRITICAL RULE: text/html is NEVER a direct file!
        is_html = (mime_type == "text/html")
        path = urlparse(current_url).path
        extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        has_direct_ext = extension in DIRECT_FILE_EXTENSIONS

        # If it's a binary stream, image, video, audio, document, or archive (not html)
        if not is_html and (
            mime_type.startswith("image/") or
            mime_type.startswith("video/") or
            mime_type.startswith("audio/") or
            mime_type in {"application/pdf", "application/zip", "application/octet-stream"} or
            has_direct_ext
        ):
            source_type = SourceType.DIRECT_FILE
            if mime_type == "application/pdf" or extension == "pdf":
                source_type = SourceType.DIRECT_FILE # or DOCUMENT_PAGE if viewer, but direct PDF file is DIRECT_FILE

            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=source_type,
                provider_id="direct_http",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.PERMITTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                mime_type=mime_type,
                estimated_size_bytes=content_length,
                redirect_chain=redirect_chain
            )

        # 7. Response is HTML Webpage. Inspect page content for embedded media
        if is_html or response_body:
            media_analysis = cls._analyze_html_media(response_body, current_url)
            page_title = media_analysis.get("title")
            video_tags = media_analysis.get("videos", [])
            images = media_analysis.get("images", [])
            has_embedded_player = media_analysis.get("has_embedded_player", False)

            if video_tags or has_embedded_player:
                return ClassificationResult(
                    original_url=url,
                    resolved_url=current_url,
                    source_type=SourceType.WEBPAGE_WITH_MEDIA,
                    provider_id="permitted_media",
                    security_status=SecurityStatus.SAFE,
                    acquisition_permission=AcquisitionPermission.PERMITTED,
                    source_access_status=SourceAccessStatus.ACCESSIBLE,
                    mime_type="text/html",
                    estimated_size_bytes=None,
                    redirect_chain=redirect_chain,
                    title=page_title,
                    extracted_media_links=video_tags
                )

            if len(images) > 3:
                return ClassificationResult(
                    original_url=url,
                    resolved_url=current_url,
                    source_type=SourceType.MEDIA_COLLECTION,
                    provider_id="permitted_media",
                    security_status=SecurityStatus.SAFE,
                    acquisition_permission=AcquisitionPermission.PERMITTED,
                    source_access_status=SourceAccessStatus.ACCESSIBLE,
                    mime_type="text/html",
                    estimated_size_bytes=None,
                    redirect_chain=redirect_chain,
                    title=page_title,
                    extracted_media_links=images
                )

            if len(images) >= 1:
                return ClassificationResult(
                    original_url=url,
                    resolved_url=current_url,
                    source_type=SourceType.WEBPAGE_WITH_MEDIA,
                    provider_id="permitted_media",
                    security_status=SecurityStatus.SAFE,
                    acquisition_permission=AcquisitionPermission.PERMITTED,
                    source_access_status=SourceAccessStatus.ACCESSIBLE,
                    mime_type="text/html",
                    estimated_size_bytes=None,
                    redirect_chain=redirect_chain,
                    title=page_title,
                    extracted_media_links=images
                )

            # Webpage without detectable media
            return ClassificationResult(
                original_url=url,
                resolved_url=current_url,
                source_type=SourceType.UNSUPPORTED_SOURCE,
                provider_id="unsupported",
                security_status=SecurityStatus.SAFE,
                acquisition_permission=AcquisitionPermission.RESTRICTED,
                source_access_status=SourceAccessStatus.ACCESSIBLE,
                mime_type="text/html",
                redirect_chain=redirect_chain,
                title=page_title,
                errors=["Webpage does not contain standalone downloadable media assets."]
            )

        # Fallback for unexpected content types
        return ClassificationResult(
            original_url=url,
            resolved_url=current_url,
            source_type=SourceType.UNSUPPORTED_SOURCE,
            provider_id="unsupported",
            security_status=SecurityStatus.SAFE,
            acquisition_permission=AcquisitionPermission.UNKNOWN,
            source_access_status=SourceAccessStatus.ACCESSIBLE,
            mime_type=mime_type,
            redirect_chain=redirect_chain,
            errors=[f"Unrecognized content type: {mime_type}"]
        )

    @classmethod
    async def _fetch_head_or_get(
        cls,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
        max_hops: int = 7
    ) -> Tuple[int, Dict[str, str], str, List[str], str]:
        current_url = url
        chain = [url]
        hops = 0
        status_code = 200
        resp_headers = {}
        body = ""

        while hops < max_hops:
            hops += 1
            # Check SSRF before making request
            safe, err = SSRFValidator.validate_url(current_url)
            if not safe:
                raise ValueError(f"SSRF violation on hop {hops} to '{current_url}': {err}")

            # Try HEAD first
            resp = await client.head(current_url, headers=headers)
            if resp.status_code in {405, 501}:
                # HEAD not allowed, do a ranged GET
                ranged_headers = dict(headers)
                ranged_headers["Range"] = "bytes=0-8192"
                resp = await client.get(current_url, headers=ranged_headers)

            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    break
                # Handle relative redirect
                from urllib.parse import urljoin
                next_url = urljoin(current_url, location)
                chain.append(next_url)
                current_url = next_url
                continue

            status_code = resp.status_code
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}

            content_type = resp_headers.get("content-type", "").lower()
            if "text/html" in content_type and status_code < 400:
                # If HTML, fetch page body (up to 256KB) to inspect media tags/JSON-LD
                try:
                    get_resp = await client.get(current_url, headers=headers)
                    body = get_resp.text[:300000]
                    resp_headers = {k.lower(): v for k, v in get_resp.headers.items()}
                    status_code = get_resp.status_code
                except Exception:
                    pass
            break

        return status_code, resp_headers, current_url, chain, body

    @classmethod
    def _extract_root_domain(cls, url: str) -> str:
        netloc = urlparse(url).netloc.lower()
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        # Remove www.
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc

    @classmethod
    def _match_platform_domain(cls, domain: str) -> Optional[str]:
        for plat_domain, plat_id in KNOWN_PLATFORM_DOMAINS.items():
            if domain == plat_domain or domain.endswith("." + plat_domain):
                return plat_id
        return None

    @classmethod
    def _analyze_html_media(cls, html: str, base_url: str) -> Dict[str, Any]:
        if not html:
            return {"title": None, "videos": [], "images": [], "has_embedded_player": False}

        # Page Title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else None

        # Videos: <video src="...">, <source src="...">, VideoObject in JSON-LD
        videos = []
        video_srcs = re.findall(r'<video[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for v in video_srcs:
            videos.append({"type": "video", "url": v})

        source_srcs = re.findall(r'<source[^>]+src=["\']([^"\']+)["\'][^>]*type=["\']video/[^"\']+["\']', html, re.IGNORECASE)
        for s in source_srcs:
            videos.append({"type": "video", "url": s})

        # JSON-LD VideoObject
        if "VideoObject" in html:
            videos.append({"type": "video_jsonld", "url": base_url})

        # Embedded iframe players (youtube, vimeo)
        has_player = bool(re.search(r'<iframe[^>]+src=["\']https?://(?:www\.)?(?:youtube\.com|player\.vimeo\.com)[^"\']+["\']', html, re.IGNORECASE))

        # Images: <img src="...">
        images = []
        img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+\.(?:png|jpg|jpeg|webp))["\']', html, re.IGNORECASE)
        for img in set(img_srcs):
            if not img.startswith("data:") and not any(ic in img.lower() for ic in ["pixel", "spacer", "tracking", "icon"]):
                images.append({"type": "image", "url": img})

        return {
            "title": title,
            "videos": videos,
            "images": images,
            "has_embedded_player": has_player
        }
