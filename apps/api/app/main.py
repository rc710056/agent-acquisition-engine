from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.config import settings
from apps.api.app.models.database import init_db
from apps.api.app.routes import (
    sources,
    acquisitions,
    approvals,
    artifacts,
    providers,
    agent_connections
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health & Observability
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

# Mount MCP Server-Sent Events (SSE) remote transport at /mcp
from services.mcp_server.server import mcp
app.mount("/mcp", mcp.sse_app())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.app.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
