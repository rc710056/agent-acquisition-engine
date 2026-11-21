# Provider Architecture & Contract

The Agent Acquisition Engine relies on pluggable provider drivers to handle diverse network sources without changing the core orchestrator.

## Base Contract (`packages/provider-contracts/base.py`)

Every provider extends `BaseProviderContract`:

```python
class BaseProviderContract(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier (e.g. 'direct_http', 'permitted_media')."""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Determines if this provider can handle the given target URL."""
        pass

    @abstractmethod
    async def inspect(self, url: str) -> SourceInspectionResult:
        """Performs initial probe, header checks, and format discovery."""
        pass

    @abstractmethod
    async def list_formats(self, url: str) -> list[FormatOption]:
        """Returns candidate formats, streams, and quality tiers."""
        pass

    @abstractmethod
    async def check_permissions(self, url: str) -> PermissionAssessment:
        """Checks if acquisition is permitted, legal, or requires approval."""
        pass

    @abstractmethod
    async def acquire(
        self,
        url: str,
        format_id: str,
        destination_path: Path,
        progress_callback: Callable[[int, Optional[int]], Awaitable[None]],
        timeout_seconds: int = 300,
    ) -> AcquisitionRawResult:
        """Streams target data to destination_path while firing progress updates."""
        pass

    @abstractmethod
    def verify(self, file_path: Path, expected: VerificationExpectation) -> VerificationResult:
        """Runs integrity checks (MIME sniffing, size, magic bytes, checksum)."""
        pass
```

## Phase 1 Provider: `direct_http`
- **Scope**: Direct downloadable binary files (`PDF`, images, archives, zip, tar, json, csv, etc.).
- **Capabilities**:
  - Controlled HEAD probe falling back to ranged GET if HEAD is forbidden (`405 Method Not Allowed`).
  - Full SSRF validation on DNS resolution and each redirect hop.
  - Streaming chunk-by-chunk download (e.g. 64KB buffers) straight to disk to prevent RAM bloat.
  - Continuous incremental SHA-256 calculation.
  - Strict size enforcement stopping execution if response exceeds maximum allowed size.
  - Safe Content-Disposition and URL-based filename extraction.

## Phase 2 Provider: `permitted_media`
- **Scope**: Authorized media streams (video, audio) using `yt-dlp` and `ffmpeg`.
- **Capabilities**:
  - Audio/video format extraction (`yt-dlp -F`).
  - Best authorized stream selection.
  - Codec extraction and container packaging.
