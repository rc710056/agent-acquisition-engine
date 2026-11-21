# Agent Acquisition Engine (AAE)

> **MCP-First File Acquisition Infrastructure for Autonomous AI Agents**

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/rc710056/agent-acquisition-engine)
[![GitHub Pages Web UI](https://img.shields.io/badge/Live%20Web%20UI-GitHub%20Pages-2563EB?logo=github)](https://rc710056.github.io/agent-acquisition-engine/)
[![CI / Tests](https://github.com/rc710056/agent-acquisition-engine/actions/workflows/deploy.yml/badge.svg)](https://github.com/rc710056/agent-acquisition-engine/actions)

Agent Acquisition Engine (AAE) provides an acquisition, inspection, verification, and artifact delivery service that AI agents access through a single Model Context Protocol (MCP) connection.

AI agents no longer need to write custom web scrapers or brittle downloaders. They delegate the entire acquisition lifecycle to AAE.

---

## 🌐 Instant Cloud Access (No Localhost Required)

You do **not** need to run this locally on `localhost`. You can run and view the entire full-stack application directly from GitHub:

1. **One-Click GitHub Codespaces**: Click the **[Open in GitHub Codespaces](https://codespaces.new/rc710056/agent-acquisition-engine)** button above. GitHub provisions a complete cloud environment with Python 3.12, Node.js 20, `aria2c`, and `ffmpeg` pre-installed, and forwards port `5173` to a secure public HTTPS preview URL.
2. **Static Web UI Preview**: Hosted on [GitHub Pages](https://rc710056.github.io/agent-acquisition-engine/).

---

## ⚡ Real Media Downloads & Architecture

Unlike mock or stub downloaders, AAE acquires **genuine, full-sized, verified media files**:
- **High-Definition Video**: Full-length 1080p/720p synchronized audio-video `.mp4` files (multi-megabyte to gigabyte master streams).
- **Pure Audio Extraction**: Studio-quality 320kbps `.mp3` and `.m4a` audio files.
- **P2P BitTorrent Protocol**: Powered by an embedded `aria2c` engine with Async DNS, DHT discovery, and multi-tracker support.
- **Multi-Step Movie Download Bypasser**: Resolves complex ad-shortened countdown redirect funnels (like MovieMod, VegaMovies, FastCloud, HubCloud) via headless browser network stream sniffing.

---

## 🏗️ Architecture Overview

```
AI AGENT
   │
   ▼ (MCP Connection: stdio / Streamable HTTP SSE)
MCP SERVER (services/mcp-server)
   │
   ▼ (Authenticated Internal API)
ACQUISITION ORCHESTRATOR (apps/api)
   │
   ▼ (Persistent Job Queue & State Machine)
PYTHON WORKER (services/acquisition-worker)
   │
   ├─► SOURCE INSPECTION (SSRF check, HEAD/probe, format detection)
   ├─► PREFLIGHT & APPROVAL (Security, quota, user confirmation gate)
   ├─► STREAMING ACQUISITION (Direct HTTP chunking, yt-dlp media extraction)
   ├─► INTEGRITY VERIFICATION (MIME sniffing, magic bytes, SHA-256)
   └─► ARTIFACT STORAGE & SIGNED DELIVERY
```

---

## 🚀 Key Capabilities (Phase 1 MVP)

- **One Consistent MCP Interface**: 7 core tools (`inspect_source`, `list_formats`, `preflight_acquisition`, `request_approval`, `start_acquisition`, `get_job_status`, `get_artifact`).
- **Direct HTTP/S Provider**: Robust chunked streaming, redirect handling, timeout bounds, and resume support.
- **SSRF & Security Isolation**: Blocks loopback, link-local, RFC-1918 private IPv4/IPv6 networks, and unsafe redirects.
- **Strict Verification Pipeline**: Non-zero check, content-length validation, magic byte verification, and SHA-256 calculation before marking jobs `completed`.
- **Human-in-the-Loop Approval Gate**: Enforces safety approvals when file sizes exceed thresholds or sensitive sources are targeted.
- **Private Artifact Delivery**: Artifacts are kept strictly private; delivery occurs exclusively via expiring signed URLs.
- **Persistent State Machine**: 14 distinct states (`created`, `understanding`, `discovering`, `inspecting`, `needs_clarification`, `awaiting_approval`, `queued`, `downloading`, `verifying`, `completed`, `partially_completed`, `failed`, `cancelled`, `expired`).

---

## 📁 Repository Structure

- `apps/api`: FastAPI backend with authentication, database models, job orchestrator, and signed URL issuer.
- `apps/web`: React/TypeScript/Vite/Tailwind human control centre.
- `services/mcp-server`: MCP protocol server exposing standard acquisition tools to agents.
- `services/acquisition-worker`: Persistent asynchronous worker process running the state machine.
- `providers/direct_http`: Direct HTTP file downloader with SSRF protection and chunked hashing.
- `providers/permitted_media`: Permitted media acquisition engine (Phase 2).
- `packages/shared-schemas`: Pydantic models and schemas shared between API, worker, and MCP server.
- `packages/provider-contracts`: Abstract base provider interfaces.
- `docs/`: Comprehensive technical architecture, security specs, and decision records.
- `tests/`: Automated unit, integration, security, and end-to-end tests.

---

## 🛠️ Quick Start (Local Development)

### 1. Requirements
- Python 3.12+
- Node.js 20+
- Git

### 2. Environment Setup
```bash
# Clone and enter directory
cd agent-acquisition-engine

# Copy configuration
cp .env.example .env

# Create Python virtual environment
uv venv --python python3.12 .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e .
```

### 3. Run Backend API
```bash
python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. Run MCP Server
```bash
python -m services.mcp_server.server
```

### 5. Run Acquisition Worker
```bash
python -m services.acquisition_worker.worker
```

### 6. Run Automated Tests
```bash
pytest tests/ -v
```

---

## 📄 Documentation

- [Project Vision & Overview](docs/PROJECT.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [REST API Specification](docs/API_SPEC.md)
- [MCP Protocol Specification](docs/MCP_SPEC.md)
- [Security & SSRF Mitigation](docs/SECURITY.md)
- [Database Schema & Migrations](docs/DATABASE.md)
- [Provider Architecture](docs/PROVIDERS.md)
- [Test Plan & Verification](docs/TEST_PLAN.md)
- [Feature Matrix & Phase Tracking](docs/FEATURE_MATRIX.md)
- [Architecture Decision Records (ADR)](docs/DECISIONS.md)
- [Known Limitations](docs/KNOWN_LIMITATIONS.md)
