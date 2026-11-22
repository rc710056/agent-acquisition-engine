from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.config import settings
from apps.api.app.models.database import init_db
from apps.api.app.routes import (
    sources,
    acquisitions,
    approvals,
    artifacts,
    providers,
    agent_connections,
    users
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables and storage exist
    await init_db()
    yield
    # Shutdown

app = FastAPI(
    title="Agent Acquisition Engine API",
    description="MCP-First File Acquisition Infrastructure for Autonomous AI Agents",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length", "Content-Disposition"],
)

@app.middleware("http")
async def capture_public_host_middleware(request: Request, call_next):
    from apps.api.app import config
    fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if fwd_host:
        clean_host = fwd_host.split(",")[0].strip()
        if not clean_host.startswith("localhost") and not clean_host.startswith("127.0.0.1"):
            proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
            config.PUBLIC_BASE_URL = f"{proto}://{clean_host}"
    return await call_next(request)

# Health & Observability
@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Agent Acquisition Engine",
        "status": "online",
        "documentation": "/docs",
        "openapi_schema": "/openapi.json",
        "mcp_sse_endpoint": "/mcp/sse",
        "web_console": "http://localhost:5173"
    }

@app.get("/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "agent-acquisition-engine",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT
    }

# Include API Routers under /api/v1
app.include_router(sources.router, prefix="/api/v1")
app.include_router(acquisitions.router, prefix="/api/v1")
app.include_router(approvals.router, prefix="/api/v1")
app.include_router(artifacts.router, prefix="/api/v1")
app.include_router(providers.router, prefix="/api/v1")
app.include_router(agent_connections.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")

# Mount MCP Server-Sent Events (SSE) remote transport at /mcp
from mcp.server.transport_security import TransportSecuritySettings
from services.mcp_server.server import mcp
app.mount(
    "/mcp",
    mcp.sse_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.app.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
