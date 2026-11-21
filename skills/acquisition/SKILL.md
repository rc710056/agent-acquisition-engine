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
- **Public MCP SSE Endpoint**: `https://difficulties-roses-cement-loud.trycloudflare.com/mcp/sse`
- **Authentication**: Bearer Token in `Authorization` header
- **Platform Secret Name**: `AAE_API_KEY`
- **Active Token**: `aae_live_c6120c81ab9f6ce84a556896a2a5dcabc8b1ba81c66b4702`

MCP Client Configuration:
```json
{
  "mcpServers": {
    "agent-acquisition-engine": {
      "url": "https://difficulties-roses-cement-loud.trycloudflare.com/mcp/sse",
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
- **Base URL**: `https://difficulties-roses-cement-loud.trycloudflare.com/api/v1` (or `http://127.0.0.1:8000/api/v1` locally)
- **Interactive OpenAPI Documentation**: `/docs`
- **Health Endpoint**: `/health`

---

## The Standard 6-Step Agent Acquisition Workflow

Whenever a user requests a file, video, or data download, execute this precise pipeline:

```
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

| Error / Symptom | Root Cause | Engine Behavior & Agent Action |
| :--- | :--- | :--- |
| `Unrecognized content type: text/plain` | Direct markdown or plain text file | Engine handles via `direct_http` provider. Select format `original`. |
| `Audio-only artifact for video format` | yt-dlp fallback `/best` matched audio | Engine enforces `[vcodec!=none]` and `ffprobe` video stream verification. |
| `Failed to download file` in remote sandbox | Download URL contained `127.0.0.1` | Engine dynamically emits public tunnel host (`https://...trycloudflare.com`). |
| `SSRF Policy Violation` | URL points to RFC-1918 or cloud metadata IP | Immediate block. Agent informs user target is forbidden. |
| `Approval Required` | Resource size exceeds threshold (>50 MB) | Call `request_approval` and obtain operator confirmation. |
| `Anti-Bot / Challenge` | Platform blocks automated scraper | Engine automatically falls back to Cobalt or Headless Chromium Sniffer. |
