from typing import List, Optional
from urllib.parse import urlparse
from packages.provider_contracts.base import BaseProviderContract
from providers.pinterest.provider import PinterestProvider
from providers.permitted_media.provider import PermittedMediaProvider
from providers.direct_http.provider import DirectHTTPProvider
from packages.source_classifier.classifier import SourceClassifier, ClassificationResult
from packages.shared_schemas.models import SecurityStatus, SourceType

class ProviderRegistryManager:
    """
    Central registry for acquisition providers.
    Routes source URLs to the appropriate provider adapter using priority-based resolution:
    1. Specialized Platform Adapters (e.g. Pinterest)
    2. Permitted Media Platforms / Webpages (yt-dlp, video/audio streams)
    3. Direct HTTP Provider (direct binary/media files only, rejects text/html)
    """

    def __init__(self):
        self._providers: List[BaseProviderContract] = []
        # Priority order: Specialized platforms first, then generic media, then direct http
        self.register(PinterestProvider())
        self.register(PermittedMediaProvider())
        self.register(DirectHTTPProvider())

    def register(self, provider: BaseProviderContract) -> None:
        self._providers.append(provider)

    def get_provider(self, provider_id: str) -> Optional[BaseProviderContract]:
        for p in self._providers:
            if p.provider_id == provider_id:
                return p
        return None

    def find_provider_for_url(self, url: str) -> Optional[BaseProviderContract]:
        """
        Fast synchronous provider lookup based on URL structure and domain matching.
        """
        if not url:
            return None
        for p in self._providers:
            if p.can_handle(url):
                return p
        return None

    async def resolve_provider_with_classifier(self, url: str) -> tuple[Optional[BaseProviderContract], ClassificationResult]:
        """
        Deep classification: resolves short URLs, checks headers, categorizes source type,
        and matches with the optimal provider.
        """
        classification = await SourceClassifier.classify(url)
        if classification.security_status == SecurityStatus.BLOCKED:
            return None, classification

        provider = self.get_provider(classification.provider_id)
        if not provider and classification.source_type != SourceType.UNSUPPORTED_SOURCE:
            # Fallback to can_handle on resolved URL only if not unsupported
            provider = self.find_provider_for_url(classification.resolved_url)
        return provider, classification

    def list_providers(self) -> List[BaseProviderContract]:
        return list(self._providers)

provider_registry = ProviderRegistryManager()
