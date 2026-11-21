# Deployment & Operations Guide

## Production Deployment
The platform is designed to be deployed using Docker Compose or Kubernetes.

### Architecture
- **Web Frontend**: Built via Vite into static assets, served by Nginx or Cloudflare Pages.
- **API Gateway**: FastAPI running under Uvicorn behind reverse proxy (port 8000).
- **MCP Server**: Stdio or Streamable HTTP/SSE service (port 8001).
- **Worker Daemon**: Persistent Python worker reading jobs from Postgres queue.
- **Database**: PostgreSQL 16+.
- **Object Storage**: S3, MinIO, or Cloudflare R2 for artifacts.

### Environment Checklist
- Set `SECRET_KEY` to a cryptographically random string (min 32 bytes).
- Set `ENVIRONMENT=production`.
- Configure `ALLOWED_ORIGINS` for CORS.
- Set `DATABASE_URL` to postgres.
- Set `ENABLE_SSRF_PROTECTION=true`.
