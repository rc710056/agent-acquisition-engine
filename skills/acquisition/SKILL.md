---
name: agent-acquisition-engine
description: Use when downloading, inspecting, or acquiring external web media, streaming videos, audio, images, archives, datasets, direct files, or torrents/magnet links through the Agent Acquisition Engine.
---

# Agent Acquisition Engine (AAE) - Operational Skill

## Overview
The **Agent Acquisition Engine (AAE)** is an enterprise-grade MCP-first gateway for automated, secure, and resilient content acquisition. It provides autonomous AI agents with verified download capabilities, anti-bot bypass, stream muxing, and cryptographic validation without guessing formats or downloading broken HTML login gates.

### Core Capabilities
- **Stream Platforms**: YouTube, Vimeo, Pinterest, Dailymotion, Reddit (automatic synchronized video+audio muxing via `ffmpeg`).
- **Galleries & Carousels**: Pinterest boards, Imgur, Reddit albums, DeviantArt, Flickr (packaged into clean `.zip` archives).
- **Direct Documents & Binaries**: PDF, TXT, Markdown, CSV, JSON, ZIP, TAR, DMG, ISO (4-way concurrent HTTP Range chunked downloader with resume support).
- **P2P & Torrents**: Native inspection and acquisition of `magnet:?xt=urn:btih:...` and `.torrent` files with tracker SSRF firewalling.
- **Dynamic JavaScript Media**: Headless Chromium network sniffer capturing live `.m3u8` (HLS) and `.mpd` (DASH) streams.
- **Deduplication Vault**: Sub-10ms instant cache fulfillment for previously verified files.
- **Integrity Guarantee**: Post-download stream-presence verification via `ffprobe` ensuring video formats never degrade to audio-only.

---

## Connection & Transports

### 1. Remote MCP Transport (Server-Sent Events) - Cloud Agents & Sandboxes
For external agent platforms (such as **Base44**, Claude Desktop, remote Sandboxes, Goose):
- **Public MCP SSE Endpoint**: `https://courage-electro-direct-derek.trycloudflare.com/mcp/sse`
- **Authentication**: Bearer Token in `Authorization` header
- **Platform Secret Name**: `AAE_API_KEY`
- **Active Token**: `aae_live_c6120c81ab9f6ce84a556896a2a5dcabc8b1ba81c66b4702`

MCP Client Configuration:
```json
{
  "mcpServers": {
    "agent-acquisition-engine": {
      "url": "https://courage-electro-direct-derek.trycloudflare.com/mcp/sse",
      "headers": {
        "Authorization": "Bearer aae_live_c6120c81ab9f6ce84a556896a2a5dcabc8b1ba81c66b4702"
      }
    }
  }
}
```

### 2. Local MCP Transport (Stdio)
For local desktop agents (Cursor, Claude Desktop, local shells):
```json
{
  "mcpServers": {
    "agent-acquisition-engine": {
      "command": "C:\\Users\\ROHIT\\.gemini\\antigravity\\scratch\\agent-acquisition-engine\\.venv\\Scripts\\python.exe",
      "args": ["-m", "services.mcp_server.server"],
      "env": {
        "API_BASE_URL": "http://127.0.0.1:8000",
        "DATABASE_URL": "sqlite+aiosqlite:///storage/aae.db",
        "STORAGE_BASE_PATH": "storage/artifacts"
      }
    }
  }
}
```

### 3. Direct REST API
- **Base URL**: `https://courage-electro-direct-derek.trycloudflare.com/api/v1` (or `http://127.0.0.1:8000/api/v1` locally)
- **Interactive OpenAPI Documentation**: `https://courage-electro-direct-derek.trycloudflare.com/docs`
- **Health Endpoint**: `https://courage-electro-direct-derek.trycloudflare.com/health`

---

## The Standard Autonomous Acquisition Workflow

Whenever a user requests a file, video, or data download, execute this precise pipeline:

```
[0. search_sources] (if user provides title/topic instead of direct URL)
        │
        ▼
[1. inspect_source] ──> [2. list_formats] ──> [3. preflight_acquisition]
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼ (if requires_approval)                                      ▼ (if can_acquire)
            [4. request_approval]                                         [5. start_acquisition]
                       │                                                             │
                       └──────────────────────────────┬──────────────────────────────┘
                                                      ▼
                                              [6. get_job_status] (poll until completed)
                                                      │
                                                      ▼
                                              [7. get_artifact] (retrieve download_url & preview_url)
```

### Step 0: Search & Intent Discovery (When no direct URL is provided)
Call `search_sources` to resolve natural language queries, movie titles, open archives, or topics into actionable sources:

**MCP Tool Call**:
```json
{
  "name": "search_sources",
  "arguments": {
    "query": "Elephants Dream",
    "kind": "video",
    "max_results": 3
  }
}
```

**Key Return Fields**:
- `candidates[]`: Array of candidate sources with `title`, `url`, `source_type`, `provider`, `thumbnail_url`, and `recommended_format_id`.
- The candidate's `url` can be passed immediately to `inspect_source` or `start_acquisition`.

---

### Step 1: Inspect Source
Call `inspect_source` to resolve short links, check SSRF safety, determine the provider, and discover formats.

**MCP Tool Call**:
```json
{
  "name": "inspect_source",
  "arguments": {
    "url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
  }
}
```

**Key Return Fields**:
- `source_id`: UUID of the registered source.
- `source_type`: `PLATFORM_MEDIA_PAGE`, `DIRECT_FILE`, `TORRENT`, `MEDIA_COLLECTION`, etc.
- `provider`: Active driver (`permitted_media`, `direct_http`, `torrent`, `pinterest`, etc.).
- `is_permitted`: `true` if passed firewall safety check.
- `recommended_format_id`: Default best format (`best_video_audio`, `original`, `all_files`).

---

### Step 2: List Formats & Multi-Option Presentation
Call `list_formats` to inspect all available streams, resolutions, and options.

**MCP Tool Call**:
```json
{
  "name": "list_formats",
  "arguments": {
    "source_id": "<source_id_from_step_1>"
  }
}
```

**Format Categorization & Selection Rules**:
1. **⭐ Recommended Video + Audio (Guaranteed Synced Streams)**:
   - `best_video_audio`: Best available resolution (e.g. 1080p/4K) muxed with highest quality audio.
   - `best_1080p_mp4`, `best_720p_mp4`, `best_360p_mp4`: Fixed resolution with audio.
   - *CRITICAL AGENT RULE*: For any video request, **ALWAYS** select a format with `has_video: true` AND `has_audio: true`.
2. **🎧 Pure Audio**:
   - `best_audio_m4a` (AAC) or `best_audio_mp3` (320k): Clean standalone audio extraction.
3. **📦 Packages & Direct Files**:
   - `original`: Direct document or binary.
   - `all_files`: Torrent or gallery archive.

**How to Present Options to the User**:
When presenting choices to the user, format them in a markdown table:
```markdown
| Option | Resolution | Codec | Stream Type | Format ID |
| :--- | :--- | :--- | :--- | :--- |
| **★ Best Quality (Recommended)** | 1080p | h264/aac | Video + Audio | `best_video_audio` |
| **Standard 720p** | 720p | h264/aac | Video + Audio | `best_720p_mp4` |
| **Compact 360p** | 360p | h264/aac | Video + Audio | `best_360p_mp4` |
| **High-Quality Audio** | - | aac | Audio Only | `best_audio_m4a` |
| **Standard MP3** | - | mp3 | Audio Only | `best_audio_mp3` |
```

---

### Step 3: Preflight Safety & Quota Check
Call `preflight_acquisition` before launching.

**MCP Tool Call**:
```json
{
  "name": "preflight_acquisition",
  "arguments": {
    "source_id": "<source_id>",
    "format_id": "best_video_audio"
  }
}
```

**Evaluating Response**:
- `is_cached: true`: File is already downloaded and verified in storage! Proceed directly to Step 7.
- `can_acquire: true` and `requires_approval: false`: Ready for immediate acquisition. Proceed to Step 5.
- `requires_approval: true`: File exceeds safety threshold (>50 MB). Request approval in Step 4.

---

### Step 4: Request Approval (If Required)
If `requires_approval: true`, call `request_approval`:

**MCP Tool Call**:
```json
{
  "name": "request_approval",
  "arguments": {
    "source_id": "<source_id>",
    "format_id": "best_video_audio",
    "reason": "Acquiring 1080p media asset requested by user"
  }
}
```
Obtain `approval_id`, and present confirmation to the operator.

---

### Step 5: Start Background Acquisition
Dispatch the acquisition job to the background worker.

**MCP Tool Call**:
```json
{
  "name": "start_acquisition",
  "arguments": {
    "source_id": "<source_id>",
    "format_id": "best_video_audio",
    "approval_id": "<approval_id_if_required>"
  }
}
```
Returns `job_id` and initial state (`queued` or `downloading`).

---

### Step 6: Monitor Job Progress
Poll `get_job_status` every 1.5–2.0 seconds until completed.

**MCP Tool Call**:
```json
{
  "name": "get_job_status",
  "arguments": {
    "job_id": "<job_id>"
  }
}
```

**Status States**:
- `downloading`: Inspect `progress_percent` (0-100%) and `bytes_transferred`.
- `verifying`: Download finished; engine is running cryptographic SHA-256 and `ffprobe` stream validation.
- `completed`: Verification succeeded. Contains `artifact_id`.
- `failed`: Check `error_message` for details.

---

### Step 7: Retrieve Verified Download & Preview Link
Call `get_artifact` to obtain the verified artifact details and public download URL.

**MCP Tool Call**:
```json
{
  "name": "get_artifact",
  "arguments": {
    "artifact_id": "<artifact_id>"
  }
}
```

**Response**:
```json
{
  "artifact_id": "art_c83fc6f8",
  "filename": "bieber_360p.mp4",
  "mime_type": "video/mp4",
  "size_bytes": 12110272,
  "sha256": "792f8a221b2c4e5f...",
  "is_verified": true,
  "download_url": "https://difficulties-roses-cement-loud.trycloudflare.com/api/v1/delivery/download?token=...",
  "preview_url": "https://difficulties-roses-cement-loud.trycloudflare.com/api/v1/delivery/download?token=...",
  "expires_at": "2026-11-21T21:45:00Z"
}
```

**Presenting Result to User**:
Always share:
1. File Name and Size (e.g. `12.11 MB`)
2. Format & Streams (e.g. `H.264 video (640x360) + AAC audio`)
3. Cryptographic SHA-256 Checksum
4. Direct Expiring Download Link: `[Download bieber_360p.mp4](download_url)`

---

## Error Handling & Edge Case Solutions

### Machine-Readable Error Envelope
Every tool returns a structured error envelope when an issue occurs:
```json
{
  "ok": false,
  "error": "Human readable error message",
  "error_code": "APPROVAL_REQUIRED",
  "error_envelope": {
    "code": "APPROVAL_REQUIRED",
    "message": "Operator approval is required (file size is unknown or exceeds 50 MB)",
    "retryable": false,
    "remediation": "Call request_approval(source_id, format_id, reason) to request operator sign-off.",
    "details": {}
  },
  "meta": {
    "timestamp": "2026-11-21T17:00:00Z",
    "engine_version": "0.2.0"
  }
}
```

### Stable Error Codes & Actions
| Error Code | Root Cause | Engine Behavior & Agent Action |
| :--- | :--- | :--- |
| `APPROVAL_REQUIRED` | File size > 50 MB or file size is unknown | Call `request_approval(source_id, format_id, reason)`. Wait for operator approval before calling `start_acquisition`. |
| `QUOTA_EXCEEDED` | File size exceeds maximum engine limit (500 MB) | Select a lower resolution/smaller format or notify operator. |
| `FORMAT_UNAVAILABLE` | Format ID requested is not offered by source | Call `list_formats(source_id)` and select a valid available `format_id`. |
| `SSRF_BLOCKED` | URL points to RFC-1918 or cloud metadata IP | Immediate block. Agent informs user destination is forbidden by security firewall. |
| `AUTH_REQUIRED` | Source requires authentication or session credentials | User authorization required before source can be fetched. |
| `NOT_FOUND` | Source, job, or artifact ID does not exist | Call `inspect_source` first to register source. |
| `UNSUPPORTED_SOURCE` | URL scheme or format has no matching provider | Inform user source type cannot be acquired. |

---

## Engine Self-Discovery: `describe_capabilities`

Agents can self-discover platform limits, active drivers, policy rules, and real-time queue depth at any time:

**MCP Tool Call**:
```json
{
  "name": "describe_capabilities",
  "arguments": {}
}
```

**Response**:
```json
{
  "ok": true,
  "engine_version": "0.2.0",
  "status": "operational",
  "active_jobs_in_queue": 3,
  "supported_protocols": ["http", "https", "magnet", "torrent", "embedded", "movie_query"],
  "rights_tiers": ["open_access", "permissive_media", "operator_approval_gated", "restricted_commercial_drm"],
  "policy_limits": {
    "max_file_size_bytes": 524288000,
    "approval_threshold_bytes": 52428800,
    "unknown_size_requires_approval": true,
    "default_timeout_seconds": 300,
    "max_retries_per_job": 3
  },
  "providers": [
    {"provider_id": "permitted_media", "display_name": "Permitted Media Provider"},
    {"provider_id": "direct_http", "display_name": "Direct HTTP/S Provider"}
  ]
}
```
