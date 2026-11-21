from fastapi import APIRouter
from typing import List, Dict, Any
from providers.registry import provider_registry

router = APIRouter(prefix="/providers", tags=["Providers"])

@router.get("", response_model=List[Dict[str, Any]])
async def list_registered_providers():
    providers = provider_registry.list_providers()
    return [
        {
            "provider_id": p.provider_id,
            "display_name": p.display_name,
            "status": "healthy",
            "supported_schemes": ["http", "https"],
            "capabilities": ["streaming", "checksum_verification", "resume", "ssrf_protection"]
        }
        for p in providers
    ]
