from typing import List, Optional
from packages.provider_contracts.base import BaseProviderContract
from providers.direct_http.provider import DirectHTTPProvider

class ProviderRegistryManager:
    """
    Central registry for acquisition providers.
    Routes source URLs to the appropriate provider adapter.
    """

    def __init__(self):
        self._providers: List[BaseProviderContract] = []
        # Register standard MVP providers
        self.register(DirectHTTPProvider())

    def register(self, provider: BaseProviderContract) -> None:
        self._providers.append(provider)

    def get_provider(self, provider_id: str) -> Optional[BaseProviderContract]:
        for p in self._providers:
            if p.provider_id == provider_id:
                return p
        return None

    def find_provider_for_url(self, url: str) -> Optional[BaseProviderContract]:
        for p in self._providers:
            if p.can_handle(url):
                return p
        return None

    def list_providers(self) -> List[BaseProviderContract]:
        return list(self._providers)

provider_registry = ProviderRegistryManager()
