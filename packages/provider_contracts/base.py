from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable
from packages.shared_schemas.models import (
    FormatOption,
    SourceInspectionResponse
)
from apps.api.app.services.verification import VerificationResult

class BaseProviderContract(ABC):
    """
    Standard interface that every acquisition provider adapter must implement.
    Allows new providers (e.g. Direct HTTP, Permitted Media, Cloud Storage)
    to plug into the engine seamlessly.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique machine-readable identifier for this provider."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name."""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Evaluates whether this provider handles the requested URL scheme and host."""
        pass

    @abstractmethod
    async def inspect(self, url: str) -> SourceInspectionResponse:
        """Inspects source availability, headers, and metadata without downloading."""
        pass

    @abstractmethod
    async def list_formats(self, url: str) -> List[FormatOption]:
        """Discovers available formats, streams, and quality representations."""
        pass

    @abstractmethod
    async def check_permissions(self, url: str) -> tuple[bool, List[str]]:
        """Checks if acquisition is allowed and any policy restrictions apply."""
        pass

    @abstractmethod
    async def acquire(
        self,
        url: str,
        format_id: str,
        destination_path: Path,
        progress_callback: Optional[Callable[[int, Optional[int]], Awaitable[None]]] = None,
        timeout_seconds: int = 300,
        max_size_bytes: int = 524_288_000,
    ) -> Dict[str, Any]:
        """
        Streams the file to disk while invoking progress_callback with byte counts.
        Returns acquisition summary dict containing total_bytes, sha256, and metadata.
        """
        pass

    @abstractmethod
    def verify(
        self,
        file_path: Path,
        expected_size: Optional[int] = None,
        expected_mime: Optional[str] = None,
        expected_sha256: Optional[str] = None
    ) -> VerificationResult:
        """Runs integrity and format validation on acquired file."""
        pass
