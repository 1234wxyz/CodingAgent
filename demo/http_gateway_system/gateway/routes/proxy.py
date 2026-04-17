"""Proxy endpoints for the demo gateway."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from gateway.dependencies import (
    RequestContext,
    get_gateway_service,
    get_request_context,
)
from gateway.models import ProxyRequest, ProxyResponse
from gateway.services.gateway import GatewayService

router = APIRouter(prefix="/proxy", tags=["proxy"])


@router.post("/{service_name}", response_model=ProxyResponse)
def proxy_to_upstream(
    service_name: str,
    payload: ProxyRequest,
    context: RequestContext = Depends(get_request_context),
    service: GatewayService = Depends(get_gateway_service),
) -> ProxyResponse:
    return service.proxy(service_name, payload, context)
