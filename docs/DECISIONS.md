# Architecture Decision Records (ADR)

## ADR-001: Modular Monorepo Architecture
- **Context**: The product involves an API gateway, MCP server, worker daemon, and frontend UI.
- **Decision**: Organize as a modular monorepo with `apps/`, `services/`, `packages/`, `providers/`.
- **Consequences**: Enables unified type definitions (`packages/shared-schemas`), consistent testing, and independent service deployability.

## ADR-002: Dual-Mode Database Strategy (PostgreSQL & SQLite)
- **Context**: Production requires PostgreSQL for concurrency; local developer setups and lightweight CI benefit from zero-configuration SQLite.
- **Decision**: Use SQLAlchemy 2.0 with async engine (`asyncpg` for PostgreSQL, `aiosqlite` for SQLite).
- **Consequences**: Complete portability without code divergence.

## ADR-003: Pure Streaming File Acquisition
- **Context**: Files can be up to 500 MB (or larger in future phases). Buffering files in worker memory would exhaust RAM and cause OOM crashes.
- **Decision**: All provider downloads stream chunks (e.g. 64KB) directly to disk temporary files while computing running SHA-256 digests.
- **Consequences**: Constant $O(1)$ memory usage regardless of file size.

## ADR-004: Standard Model Context Protocol (MCP) Server
- **Context**: External AI agents (Claude, Antigravity, OpenAI) need an official, uniform protocol.
- **Decision**: Build an MCP-compliant server exposing 7 structured tools over Stdio and Streamable HTTP (SSE).
- **Consequences**: Standard interoperability with modern agent runtimes.
