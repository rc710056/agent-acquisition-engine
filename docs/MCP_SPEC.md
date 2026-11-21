# Model Context Protocol (MCP) Server Specification

The Agent Acquisition Engine MCP Server implements the standard Model Context Protocol over Stdio and Streamable HTTP (SSE). External AI agents configure this server in their client settings to gain file acquisition tools.

## Supported MCP Tools

### 1. `inspect_source`
- **Description**: Probes a target URL or identifier, assesses SSRF safety and permissions, and returns source metadata.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "url": {"type": "string", "description": "Target file or resource URL"},
      "user_preferences": {"type": "object", "description": "Optional format/quality preferences"}
    },
    "required": ["url"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "source_id": "string",
    "provider": "string",
    "is_permitted": "boolean",
    "capabilities": ["string"],
    "mime_type": "string",
    "estimated_size_bytes": "integer | null",
    "inspection_status": "string",
    "errors": ["string"]
  }
  ```

### 2. `list_formats`
- **Description**: Lists available downloadable formats, streams, audio/video resolutions, or codecs for an inspected source.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "source_id": {"type": "string", "description": "The source ID returned by inspect_source"}
    },
    "required": ["source_id"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "source_id": "string",
    "formats": [
      {
        "format_id": "string",
        "file_type": "string",
        "mime_type": "string",
        "resolution": "string | null",
        "codec": "string | null",
        "estimated_size_bytes": "integer | null",
        "quality_label": "string"
      }
    ]
  }
  ```

### 3. `preflight_acquisition`
- **Description**: Validates that acquisition can proceed, checking storage quotas, file size boundaries, and approval requirements.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "source_id": {"type": "string"},
      "format_id": {"type": "string"},
      "execution_mode": {"type": "string", "enum": ["cloud", "local"], "default": "cloud"}
    },
    "required": ["source_id", "format_id"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "can_acquire": "boolean",
    "requires_approval": "boolean",
    "approval_reason": "string | null",
    "estimated_size_bytes": "integer | null",
    "storage_available": "boolean",
    "duplicate_artifact_id": "string | null"
  }
  ```

### 4. `request_approval`
- **Description**: Initiates a human-in-the-loop approval workflow for restricted, high-bandwidth, or sensitive files.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "source_id": {"type": "string"},
      "format_id": {"type": "string"},
      "reason": {"type": "string", "description": "Why the agent wants to acquire this file"}
    },
    "required": ["source_id", "format_id"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "approval_id": "string",
    "status": "pending",
    "message": "string"
  }
  ```

### 5. `start_acquisition`
- **Description**: Submits an acquisition task to the engine and transitions the job to queued.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "source_id": {"type": "string"},
      "format_id": {"type": "string"},
      "approval_id": {"type": "string", "description": "Required if preflight indicated approval is needed"},
      "execution_mode": {"type": "string", "enum": ["cloud", "local"], "default": "cloud"}
    },
    "required": ["source_id", "format_id"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "job_id": "string",
    "state": "queued",
    "execution_mode": "string",
    "created_at": "string"
  }
  ```

### 6. `get_job_status`
- **Description**: Queries real-time telemetry, byte progress, active state, and event history for a job.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "job_id": {"type": "string"}
    },
    "required": ["job_id"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "job_id": "string",
    "state": "string",
    "progress_percent": "number | null",
    "bytes_transferred": "integer",
    "total_bytes": "integer | null",
    "current_operation": "string",
    "artifact_id": "string | null",
    "error_message": "string | null"
  }
  ```

### 7. `get_artifact`
- **Description**: Returns verified metadata and a cryptographically signed expiring retrieval link for a completed acquisition.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "artifact_id": {"type": "string"}
    },
    "required": ["artifact_id"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "artifact_id": "string",
    "filename": "string",
    "mime_type": "string",
    "size_bytes": "integer",
    "sha256": "string",
    "download_url": "string",
    "expires_at": "string"
  }
  ```

## Error Handling & Honesty Contract
- All errors return structured MCP error responses with standard codes (`INVALID_PARAMS`, `INTERNAL_ERROR`, `PERMISSION_DENIED`).
- Never return placeholder data. If size cannot be computed before download, `estimated_size_bytes` is `null`.
- Unfinished or failed downloads never return an artifact download URL.
