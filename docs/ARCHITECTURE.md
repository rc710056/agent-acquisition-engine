# System Architecture: Agent Acquisition Engine

```mermaid
flowchart TD
    subgraph ClientLayer [Client & Agent Layer]
        Agent[Autonomous AI Agent]
        WebUI[React Operator Dashboard]
    end

    subgraph InterfaceLayer [Interface & Protocol Layer]
        MCPServer[MCP Server: Streamable HTTP / SSE / Stdio]
        APIGateway[FastAPI Application Gateway]
    end

    subgraph CoreEngine [Core Orchestrator & State Management]
        JobDB[(Relational DB: SQLite / Postgres)]
        Queue[Persistent State Machine Job Queue]
        Orchestrator[Acquisition Orchestrator Service]
    end

    subgraph WorkerLayer [Execution & Worker Layer]
        Worker[Persistent Python Worker Pool]
        SSRFEngine[SSRF & URL Security Validator]
        VerificationEngine[File Verification & Checksum Engine]
    end

    subgraph ProviderLayer [Provider Adapters]
        DirectHTTP[Direct HTTP / S Provider]
        PermittedMedia[Permitted Media Provider: yt-dlp / ffmpeg]
        OfficialAPI[Official API Provider]
    end

    subgraph StorageLayer [Secure Artifact Storage]
        LocalStorage[Local Filesystem Storage]
        S3Storage[S3-Compatible Object Store]
    end

    Agent -->|Model Context Protocol| MCPServer
    MCPServer -->|Internal Authenticated API| APIGateway
    WebUI -->|REST / SSE Telemetry| APIGateway
    APIGateway --> Orchestrator
    Orchestrator --> JobDB
    Orchestrator --> Queue
    Queue --> Worker
    Worker --> SSRFEngine
    Worker --> ProviderLayer
    ProviderLayer --> DirectHTTP
    ProviderLayer --> PermittedMedia
    ProviderLayer --> OfficialAPI
    Worker --> VerificationEngine
    Worker --> StorageLayer
    StorageLayer --> LocalStorage
    StorageLayer --> S3Storage
```

## Architectural Decoupling

1. **MCP Server (`services/mcp-server`)**:
   Exposes standard MCP endpoints (`inspect_source`, `list_formats`, `preflight_acquisition`, `request_approval`, `start_acquisition`, `get_job_status`, `get_artifact`). It acts as a lightweight protocol translator, delegating all operations to the core API over authenticated internal transport.

2. **API Gateway (`apps/api`)**:
   FastAPI application managing REST routes, JWT/API-key authentication, user session ownership, database ORM persistence, signed download link generation, and audit logging.

3. **Persistent Worker (`services/acquisition-worker`)**:
   A dedicated background daemon that continuously polls for `queued` jobs, executes provider-specific downloads via streaming chunk pipes, runs integrity verification, writes artifacts to storage, and writes granular `job_events`.

4. **Provider Adapter Interface (`packages/provider-contracts`)**:
   All source handlers implement `BaseProviderContract`:
   - `can_handle(source: SourceReference) -> bool`
   - `inspect(source: SourceReference) -> SourceInspectionResult`
   - `list_formats(source: SourceReference) -> list[FormatOption]`
   - `check_permissions(source: SourceReference) -> PermissionAssessment`
   - `acquire(selection: AcquisitionSelection, progress_callback) -> AcquisitionRawResult`
   - `verify(raw_file: Path, expected: VerificationExpectation) -> VerificationResult`

5. **Storage Abstraction (`apps/api/app/services/storage.py`)**:
   Supports local filesystem and S3. Direct external access to raw paths is disabled; all file downloads flow through an expiring signed HMAC token endpoint.
