"""Health endpoints for the demo gateway."""

from __future__ import annotations

from fastapi import APIRouter

from gateway.config import load_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck() -> dict:
    settings = load_settings()
    return {
        "status": "ok",
        "gateway": settings.gateway_name,
        "services": [item.service for item in settings.upstreams],
    }
