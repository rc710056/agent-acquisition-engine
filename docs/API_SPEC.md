# REST API Specification

Base URL: `http://localhost:8000/api/v1`

## Authentication
Requests must supply a bearer token or API key header:
`Authorization: Bearer <API_KEY_OR_JWT>`

---

## Endpoints

### 1. Health & Readiness
- `GET /health`
  - 200 OK: `{"status": "ok", "db": "connected", "worker": "active"}`

### 2. Source Inspection
- `POST /sources/inspect`
  - Body:
    ```json
    {
      "url": "https://example.com/document.pdf",
      "user_preferences": {"preferred_format": "pdf"}
    }
    ```
  - Returns:
    ```json
    {
      "source_id": "src_01hf...",
      "url": "https://example.com/document.pdf",
      "provider_id": "direct_http",
      "is_permitted": true,
      "capabilities": ["direct_stream", "resume"],
      "mime_type": "application/pdf",
      "estimated_size_bytes": 1048576,
      "status": "inspected",
      "errors": []
    }
    ```

### 3. List Formats
- `GET /sources/{source_id}/formats`
  - Returns array of format objects:
    ```json
    [
      {
        "format_id": "orig_pdf",
        "file_type": "document",
        "mime_type": "application/pdf",
        "resolution": null,
        "codec": null,
        "estimated_size_bytes": 1048576,
        "quality_label": "original"
      }
    ]
    ```

### 4. Preflight Check
- `POST /acquisitions/preflight`
  - Body:
    ```json
    {
      "source_id": "src_01hf...",
      "format_id": "orig_pdf",
      "execution_mode": "cloud"
    }
    ```
  - Returns:
    ```json
    {
      "can_acquire": true,
      "requires_approval": false,
      "estimated_size_bytes": 1048576,
      "storage_available": true,
      "duplicate_artifact_id": null
    }
    ```

### 5. Approval Workflow
- `POST /approvals/request`
  - Creates a pending approval request.
- `GET /approvals/{approval_id}`
  - Fetches approval status (`pending`, `approved`, `rejected`).
- `POST /approvals/{approval_id}/decision`
  - Body: `{"decision": "approved"}` (User or admin token required).

### 6. Acquisition Jobs
- `POST /jobs`
  - Body:
    ```json
    {
      "source_id": "src_01hf...",
      "format_id": "orig_pdf",
      "approval_id": "appr_...",
      "execution_mode": "cloud"
    }
    ```
  - Returns 201 Created: `{"job_id": "job_01hf...", "state": "queued"}`

- `GET /jobs/{job_id}`
  - Returns full job telemetry, current state, progress percentage, transferred bytes, and errors.

- `POST /jobs/{job_id}/cancel`
  - Cancels a running or queued job.

### 7. Artifacts & Signed Delivery
- `GET /artifacts/{artifact_id}`
  - Returns artifact metadata:
    ```json
    {
      "artifact_id": "art_01hf...",
      "filename": "document.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 1048576,
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "verified": true,
      "download_url": "http://localhost:8000/api/v1/delivery/download?token=eyJhbGciOi...",
      "expires_at": "2026-11-21T12:00:00Z"
    }
    ```

- `GET /delivery/download?token=...`
  - Validates cryptographic HMAC signature and expiry, then streams file binary to client.
