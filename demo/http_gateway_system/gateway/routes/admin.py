"""Admin endpoints for the demo gateway."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from gateway.dependencies import (
    RequestContext,
    get_gateway_service,
    get_request_context,
)
from gateway.services.gateway import GatewayService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/routes")
def list_routes(
    context: RequestContext = Depends(get_request_context),
    service: GatewayService = Depends(get_gateway_service),
) -> dict:
    return {
        "gateway": context.gateway_name,
        "actor": context.actor,
        "routes": service.list_routes(),
        "recent_audit_events": service.recent_events(),
    }
