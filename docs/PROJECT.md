# Project Vision & Charter: Agent Acquisition Engine (AAE)

## 1. Problem Statement
Autonomous AI agents are increasingly tasked with gathering evidence, reading source papers, analyzing datasets, and processing multimedia assets. Today, each agent framework attempts to download files independently using simplistic HTTP libraries or headless browsers.

This approach fails in production environments:
1. **Security Vulnerabilities**: Naive downloaders are vulnerable to SSRF (accessing cloud metadata `169.254.169.254`, localhost admin ports, internal services), zip bombs, and arbitrary code execution.
2. **Fragility & Protocol Errors**: Handling chunked transfer, ranged resume, redirect chains, content-disposition filenames, and provider throttling requires sophisticated engineering.
3. **Format Blindness**: Agents lack awareness of available stream bitrates, audio codecs, and file formats, often downloading inefficient or unusable media.
4. **Lack of Human Oversight**: Agents make uncontrolled downloads of oversized or restricted resources without approval gates.
5. **Storage Sprawl & Invalidation**: Without centralized verification and signed retrieval URLs, downloaded artifacts leak across environments.

## 2. Core Value Proposition
The Agent Acquisition Engine (AAE) acts as a centralized, high-integrity acquisition utility for the AI agent ecosystem. Agents interact through standard Model Context Protocol (MCP) tools:
- They declare what source needs inspection.
- They inspect candidate formats and estimated resource demands.
- They preflight permissions and obtain user approval when required.
- They trigger acquisition jobs handled by a resilient background worker.
- They receive verified, checksummed artifacts via expiring signed links.

## 3. Product Principles
- **One Engine, Many Agents**: Standardized MCP tools allow Claude, OpenAI, Antigravity, or custom agents to share the infrastructure.
- **Pluggable Providers**: Modular adapters for Direct HTTP, permitted media (yt-dlp/ffmpeg), and official APIs.
- **Honest Telemetry**: Never fabricate file sizes, simulated progress, or fake successes. If metadata is unknown, report `unknown`.
- **Zero-Trust Security**: Strict SSRF defenses, path traversal immunity, MIME sniffing, magic byte matching, and private storage default.
- **Cost Conscious**: Streaming pipeline (no buffering 500MB into memory), content deduplication, and open-source foundation.
