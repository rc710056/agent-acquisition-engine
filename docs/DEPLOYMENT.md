# Deployment & Operations Guide

## Production Deployment
The platform is designed to be deployed using Docker Compose or Kubernetes.

### Architecture
- **Web Frontend**: Built via Vite into static assets, served by Nginx or Cloudflare Pages.
- **API Gateway**: FastAPI running under Uvicorn behind reverse proxy (port 8000).
- **MCP Server**: Stdio for local clients; authenticated SSE is mounted on the API at `/mcp/sse` (port 8000). The stdio process does not listen on a TCP port.
- **Worker Daemon**: Persistent Python worker reading jobs from Postgres queue.
- **Database**: PostgreSQL 16+.
- **Object Storage**: S3, MinIO, or Cloudflare R2 for artifacts.

### Environment Checklist
- Set `SECRET_KEY` to a unique cryptographically random string (at least 32 characters). Production startup rejects the development-only key.
- Set `POSTGRES_PASSWORD` to a unique random hexadecimal password; the database port is not published to the host.
- Set `ENVIRONMENT=production`.
- Set `API_BASE_URL` to the externally reachable HTTPS API base URL and configure `CORS_ORIGINS` as a JSON array containing only the deployed UI origins.
- Set `DATABASE_URL` to postgres.
- Set `ENABLE_SSRF_PROTECTION=true`.
- Give each agent its own API key and only the `read` and `acquire` permissions it needs. Keep keys in the MCP client's bearer-header or process environment, never in tool arguments, source control, or logs.
- Place the API behind HTTPS and a reverse proxy, and apply outbound network restrictions in addition to the application's SSRF checks.
- The production user bootstrap/invitation flow is not implemented yet; provision users through a trusted administrative process before enabling external access.
