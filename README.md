# Agent Acquisition Engine (AAE)

> **MCP-First File Acquisition Infrastructure for Autonomous AI Agents**

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/rc710056/agent-acquisition-engine)
[![GitHub Pages Web UI](https://img.shields.io/badge/Live%20Web%20UI-GitHub%20Pages-2563EB?logo=github)](https://rc710056.github.io/agent-acquisition-engine/)
[![CI / Tests](https://github.com/rc710056/agent-acquisition-engine/actions/workflows/deploy.yml/badge.svg)](https://github.com/rc710056/agent-acquisition-engine/actions)

Agent Acquisition Engine (AAE) provides an acquisition, inspection, verification, and artifact delivery service that AI agents access through a single Model Context Protocol (MCP) connection.

AI agents no longer need to write custom web scrapers or brittle downloaders. They delegate the entire acquisition lifecycle to AAE.

---

## 🌐 Hosted UI and API

The GitHub Pages site is a static UI preview; acquisition requires a separately deployed API, worker, database, and storage service. Codespaces is a development environment, not a production hosting or security boundary.

- **Development:** Open the repository in [GitHub Codespaces](https://codespaces.new/rc710056/agent-acquisition-engine).
- **Static UI preview:** [GitHub Pages](https://rc710056.github.io/agent-acquisition-engine/).

---

## 📦 Acquisition scope

AAE is a provider-based acquisition service, not a universal downloader. Supported sources, file types, and output formats depend on the enabled provider and its upstream rules. The direct HTTP provider handles direct file URLs; platform media and specialized providers have separate support and limitations. A successful inspection is not proof that a source is licensed for reuse.

The service does not bypass DRM, paywalls, CAPTCHAs, or source authentication. Users should only acquire content they are authorized to access and store.

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

- **One Consistent MCP Interface**: 8 tools for inspection, format selection, approval, acquisition, job status, and artifact delivery.
- **Direct HTTP/S Provider**: Robust chunked streaming, redirect handling, timeout bounds, and resume support.
- **SSRF & Security Isolation**: Direct HTTP transfers block non-global targets and validate each redirect hop. Production deployments must also restrict network egress, especially for third-party providers.
- **Strict Verification Pipeline**: Non-zero check, content-length validation, magic byte verification, and SHA-256 calculation before marking jobs `completed`.
- **Human-in-the-Loop Approval Gate**: New acquisitions require user approval for files larger than 50 MB or with unknown size. Reusing an already-verified artifact in the same user's vault does not trigger a new approval. The configured maximum is 500 MB by default.
- **Scoped Agent Credentials**: Agent keys can inspect and acquire only within their granted permissions; they cannot approve jobs or retrieve user portal tokens.
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

For local stdio access, configure `MCP_AUTH_TOKEN` in the MCP client's process environment with an agent API key. Do not put credentials in tool arguments or commit them to the repository. This command uses the local database and storage configured for this checkout; it does not connect to a separately hosted deployment.

For remote clients, use the authenticated SSE endpoint mounted by the API at `/mcp/sse` and send the agent API key in the `Authorization: Bearer ...` header.

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
