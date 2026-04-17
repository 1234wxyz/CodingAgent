"""FastAPI dependencies for the demo gateway.

This module intentionally contains a startup bug for the interview demo.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from gateway.container import get_container
from gateway.services.auth import ApiKeyAuthenticator
from gateway.services.gateway import GatewayService


@dataclass
class RequestContext:
    actor: str
    trace_id: str
    gateway_name: str


def get_authenticator() -> ApiKeyAuthenticator:
    return get_container().authenticator


def get_gateway_service() -> GatewayService:
    return get_container().gateway_service


def get_request_context(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> RequestContext:
    container = get_container()
    authenticator = get_authenticator()
    try:
        actor = authenticator.authenticate(x_api_key)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    trace_id = getattr(request.state, "request_id", "req-missing")
    return RequestContext(
        actor=actor,
        trace_id=trace_id,
        gateway_name=container.settings.gateway_name,
    )
