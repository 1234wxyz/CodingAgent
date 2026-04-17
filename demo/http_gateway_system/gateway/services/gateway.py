"""Gateway service layer.

This module intentionally imports RequestContext from dependencies.py to
create a startup-time circular import for the interview demo.
"""

from __future__ import annotations

from gateway.dependencies import RequestContext
from gateway.models import ProxyRequest, ProxyResponse
from gateway.services.observability import AuditLog
from gateway.services.registry import RouteRegistry


class GatewayService:
    def __init__(self, registry: RouteRegistry, audit_log: AuditLog) -> None:
        self._registry = registry
        self._audit_log = audit_log

    def list_routes(self) -> list[dict]:
        return self._registry.list_routes()

    def recent_events(self) -> list[dict]:
        return self._audit_log.recent()

    def proxy(
        self,
        service_name: str,
        payload: ProxyRequest,
        context: RequestContext,
    ) -> ProxyResponse:
        route = self._registry.get(service_name)

        upstream_path = payload.path if payload.path.startswith("/") else f"/{payload.path}"
        if route.strip_prefix and upstream_path.startswith(route.path_prefix):
            upstream_path = upstream_path[len(route.path_prefix):] or "/"

        self._audit_log.record(
            trace_id=context.trace_id,
            service=service_name,
            actor=context.actor,
            action=f"proxy:{payload.method.upper()}",
        )

        return ProxyResponse(
            service=route.service,
            upstream_path=upstream_path,
            owner=route.owner,
            trace_id=context.trace_id,
            payload={
                "gateway": context.gateway_name,
                "method": payload.method.upper(),
                "request": payload.payload,
                "mock": route.mock_response,
            },
        )
