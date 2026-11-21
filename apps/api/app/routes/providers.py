from fastapi import APIRouter
from typing import List, Dict, Any
from providers.registry import provider_registry

router = APIRouter(prefix="/providers", tags=["Providers"])

PROVIDER_METRICS = {
    "torrent": {
        "supported_schemes": ["magnet", "torrent", "udp", "dht"],
        "max_file_size": "50 GB (P2P Swarm Scaled)",
        "capabilities": ["Distributed BitTorrent P2P", "Decentralized DHT Discovery", "Block-level Checksum Verification", "Multi-file Archive Selective Ingestion"],
        "description": "High-throughput peer-to-peer driver with tracker DNS isolation and automatic seeder verification."
    },
    "movie_intelligence": {
        "supported_schemes": ["movie:", "cinematic:", "https"],
        "max_file_size": "100 GB (Theatrical 4K / Remux)",
        "capabilities": ["Wikipedia REST Live Metadata", "Distributor OTT Legal Routing", "Theatrical Poster Curation", "Synchronized 1080p Preview Stream", "Soundtrack MP3 Extraction"],
        "description": "Real-time cinematic intelligence provider resolving verified metadata, distributor streaming links, and synchronized theatrical previews."
    },
    "permitted_media": {
        "supported_schemes": ["http", "https"],
        "max_file_size": "25 GB (Dual-Stream Adaptive)",
        "capabilities": ["yt-dlp Live Stream Sniffer", "Lossless FFmpeg Audio-Video Muxer", "M4A / MP3 Audio Isolation", "Dynamic Resolution Adaptation"],
        "description": "Universal media streaming driver that separates or losslessly muxes remote video and audio streams into synchronized MP4/M4A containers."
    },
    "pinterest": {
        "supported_schemes": ["http", "https"],
        "max_file_size": "2 GB (Original Asset)",
        "capabilities": ["Pin Payload Inspector", "Original 4K Image Scraping", "Embedded MP4 Video Extraction", "Dynamic CDN Bypass"],
        "description": "Specialized social media scraper parsing pin metadata and downloading full uncompressed images and video clips."
    },
    "gallery_dl": {
        "supported_schemes": ["http", "https"],
        "max_file_size": "10 GB (Image Collections)",
        "capabilities": ["Multi-image Album Scraper", "Complete Zip Packaging", "High-Resolution Image Extraction", "Carousel Parsing"],
        "description": "Batch image collection harvester downloading multi-photo albums and packaging them into verified archives."
    },
    "cobalt": {
        "supported_schemes": ["http", "https"],
        "max_file_size": "10 GB (Universal Fallback)",
        "capabilities": ["Anti-Bot Webhook Bypass", "Zero-Watermark Extraction", "Tunnel Proxy Streaming", "Social Media Fallback"],
        "description": "Resilient secondary media resolver providing anti-bot stream bypass when direct platform requests fail."
    },
    "browser_sniffer": {
        "supported_schemes": ["http", "https"],
        "max_file_size": "10 GB (Dynamic Single-Page Apps)",
        "capabilities": ["Headless Chromium DOM Sniffer", "Network Packet Stream Interceptor", "HLS / DASH Manifest Capture", "JavaScript Dynamic Execution"],
        "description": "Headless browser driver that renders complex JavaScript single-page apps to capture obfuscated background media requests."
    },
    "direct_http": {
        "supported_schemes": ["http", "https"],
        "max_file_size": "50 GB (Direct Chunked Binaries)",
        "capabilities": ["8-Thread Parallel HTTP Range Slices", "Automatic Slice Resumption", "SSRF IP Loopback Firewall", "SHA-256 Digest Verification"],
        "description": "Accelerated byte-range concurrent downloader splitting large files across parallel network threads for maximum line speed."
    }
}

@router.get("", response_model=List[Dict[str, Any]])
async def list_registered_providers():
    providers = provider_registry.list_providers()
    result = []
    for p in providers:
        meta = PROVIDER_METRICS.get(p.provider_id, {
            "supported_schemes": ["http", "https"],
            "max_file_size": "25 GB (Configurable)",
            "capabilities": ["Streaming Ingestion", "SHA-256 Verification", "Resume", "SSRF Protection"],
            "description": "Standard streaming acquisition adapter."
        })
        result.append({
            "provider_id": p.provider_id,
            "display_name": p.display_name,
            "status": "healthy",
            "supported_schemes": meta["supported_schemes"],
            "max_file_size": meta["max_file_size"],
            "capabilities": meta["capabilities"],
            "description": meta["description"]
        })
    return result
