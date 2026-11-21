---
name: agent-acquisition-engine
description: Use when downloading, inspecting, or acquiring external web media, streaming videos, audio, images, archives, datasets, direct files, or torrents/magnet links through the Agent Acquisition Engine.
---

# Agent Acquisition Engine (AAE) - Operational Skill

## Overview
The **Agent Acquisition Engine (AAE)** is an enterprise-grade MCP-first gateway for automated, secure, and resilient content acquisition. It prevents common agent failure modes (such as downloading HTML login gates instead of video streams, downloading audio-less video tracks, or crashing on JavaScript-rendered blobs and magnet links).

### Core Capabilities
- **Stream Platforms**: YouTube, Pinterest, Vimeo, Dailymotion, Reddit video (automatic video+audio muxing via `ffmpeg`).
- **Galleries & Carousels**: Pinterest boards, Imgur, Reddit albums, DeviantArt, Flickr (packaged into clean `.zip` archives).
- **Direct Binaries & Large Files**: 4-way concurrent HTTP Range chunked downloader with resume support.
- **P2P & Torrents**: Native inspection and acquisition of `magnet:?xt=urn:btih:...` and `.torrent` files with tracker SSRF firewalling.
- **Dynamic JavaScript Media**: Headless Chromium network sniffer capturing live `.m3u8` (HLS) and `.mpd` (DASH) streams.
- **Content Deduplication Cache**: Sub-10ms instant returns for previously verified files.

---

## Connection & Transports

### 1. Model Context Protocol (MCP) - Stdio
Add to your agent configuration (Claude Desktop, Cursor, Goose, Cline):
```json
{
  "mcpServers": {
    "agent-acquisition-engine": {
      "command": "C:\\Users\\ROHIT\\.gemini\\antigravity\\scratch\\agent-acquisition-engine\\.venv\\Scripts\\python.exe",
      "args": ["-m", "services.mcp_server.server"],
      "env": {
        "DATABASE_URL": "sqlite+aiosqlite:///storage/aae.db",
        "STORAGE_BASE_PATH": "storage/artifacts"
      }
    }
  }
}
```

### 2. Remote MCP Transport (Server-Sent Events)
Connect to the running FastAPI gateway:
- **SSE Endpoint**: `http://127.0.0.1:8000/mcp/sse`
- **Messages Endpoint**: `http://127.0.0.1:8000/mcp/messages`

### 3. Direct REST API
- **API Base**: `http://127.0.0.1:8000/api/v1`
- **Interactive OpenAPI Docs**: `http://127.0.0.1:8000/docs`

---

## The Standard 5-Step Agent Acquisition Workflow

Whenever a user requests a file, video, or data download, execute this precise pipeline:

### Step 1: Inspect Source
Call `inspect_source` to resolve short links, check SSRF safety, determine the provider, and discover formats.

**MCP Tool Call**:
```json
{
  "name": "inspect_source",
  "arguments": {
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  }
}
```

**Key Return Fields**:
- `source_id`: UUID of the registered source.
- `recommended_format_id`: Default best format (`best_video_audio`, `all_files`, `original`).
- `capabilities`: Available engine capabilities (`media_extraction`, `chunked_download`, `p2p_torrent`, etc.).

---

### Step 2: Select Format with Audio Guarantee
**CRITICAL RULE**: Never select raw video streams (e.g. `249`, `137`) that lack audio unless the user explicitly requested a mute video.

Use these standardized format IDs:
| User Intent | Format ID | Behavior |
| :--- | :--- | :--- |
| **Highest Quality Video** | `best_video_audio` | Merges best video + best audio into `.mp4` |
| **Full HD 1080p** | `best_1080p_mp4` | 1080p video muxed with high-bitrate audio |
| **Standard 720p** | `best_720p_mp4` | 720p video muxed with audio |
| **Audio Only (Music/Podcast)**| `best_audio_mp3` or `best_audio_m4a` | Clean audio track extraction |
| **Torrent / Archive** | `all_files` | Full package archive with manifest |
| **Direct File** | `original` | High-speed concurrent chunked download |

Call `list_formats(source_id)` if you need to browse all specific resolutions and file sizes.

---

### Step 3: Preflight Safety & Approval Check
Call `preflight_acquisition` before launching.

**MCP Tool Call**:
```json
{
  "name": "preflight_acquisition",
  "arguments": {
    "source_id": "src_12345",
    "format_id": "best_video_audio"
  }
}
```

**Evaluating Response**:
- If `is_cached: true`: The artifact is already downloaded and verified on disk! You can immediately retrieve it.
- If `requires_approval: true`: The file exceeds the safety threshold (e.g. >50 MB) or requires manual operator sign-off.
  - Inform the user: *"This download is estimated at X MB and requires operator confirmation in the Approvals tab at http://localhost:5173/approvals."*
  - Do not proceed until approved.

---

### Step 4: Dispatch & Monitor Acquisition
Launch the background job and poll until complete.

**MCP Tool Call**:
```json
{
  "name": "start_acquisition",
  "arguments": {
    "source_id": "src_12345",
    "format_id": "best_video_audio"
  }
}
```

**Monitor Status**:
Call `get_acquisition_status(job_id)` every 2 seconds:
- `state == "completed"`: Acquisition finished and magic-byte verified. Contains `artifact_id`.
- `state == "downloading"`: Check `progress_percent` and `bytes_transferred`.
- `state == "failed"`: Check `error_message` for diagnosis.

---

### Step 5: Deliver Verified Artifact
Once completed, call `download_artifact(artifact_id)`.

**MCP Tool Call**:
```json
{
  "name": "download_artifact",
  "arguments": {
    "artifact_id": "art_12345"
  }
}
```

**Returns**:
- `local_path`: Absolute path to verified file on disk (e.g. `C:\Users\ROHIT\...`).
- `delivery_url`: Signed HTTP download link with HMAC security token.
- `sha256`: Cryptographic hash verifying file integrity.
- `mime_type`: Magic-byte verified MIME type.

Present the file path and summary clearly to the user.

---

## Autonomous Decision Matrix

```
User Prompt: "Download https://pin.it/zRhGMggGP"
  ↳ Agent calls inspect_source("https://pin.it/zRhGMggGP")
  ↳ Engine resolves short link -> detects Pinterest video
  ↳ Agent selects format_id="best_video_audio"
  ↳ Agent checks preflight -> dispatches job -> verifies -> presents .mp4 file

User Prompt: "Grab this dataset magnet:?xt=urn:btih:3b245504..."
  ↳ Agent calls inspect_source(magnet_url)
  ↳ Engine verifies tracker SSRF safety -> extracts torrent metadata
  ↳ Agent selects format_id="all_files"
  ↳ Engine downloads package -> verifies SHA-256 -> delivers .zip artifact

User Prompt: "Download large archive https://example.com/data.tar.gz"
  ↳ Agent calls inspect_source(url)
  ↳ Engine identifies DIRECT_FILE with Accept-Ranges
  ↳ Engine activates 4-way concurrent chunked downloader
  ↳ Downloads 4x faster with byte-level resumption -> delivers verified .tar.gz
```

---

## Error Handling & Troubleshooting

| Error Code / Symptom | Root Cause | Agent Action |
| :--- | :--- | :--- |
| `SSRF Policy Violation` | URL targets private network or cloud metadata | Refuse target; inform user private IPs are forbidden. |
| `Approval Required` | File exceeds policy threshold (>50MB) | Instruct user to approve at `http://localhost:5173/approvals`. |
| `Anti-Bot / Challenge` | Platform rate limits unauthenticated requests | PermittedMediaProvider will automatically fallback to Cobalt or Browser Sniffer. |
| `Invalid State Transition` | Job was already completed from cache | Use cached `artifact_id` directly; skip download step. |
