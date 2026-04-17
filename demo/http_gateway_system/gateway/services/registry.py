"""Upstream registry used by the demo gateway."""

from __future__ import annotations

from gateway.models import RouteSummary, UpstreamDefinition


class RouteRegistry:
    def __init__(self, upstreams: list[UpstreamDefinition]) -> None:
        self._routes = {item.service: item for item in upstreams}

    def get(self, service_name: str) -> UpstreamDefinition:
        try:
            return self._routes[service_name]
        except KeyError as exc:
            raise KeyError(f"Unknown upstream service: {service_name}") from exc

    def list_routes(self) -> list[dict]:
        summaries = [
            RouteSummary(
                service=item.service,
                path_prefix=item.path_prefix,
                owner=item.owner,
                timeout_ms=item.timeout_ms,
            )
            for item in self._routes.values()
        ]
        return [summary.model_dump() for summary in summaries]
