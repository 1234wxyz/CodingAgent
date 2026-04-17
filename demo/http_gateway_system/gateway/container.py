"""Simple service container used by the demo gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway.models import GatewaySettings


@dataclass
class GatewayContainer:
    settings: GatewaySettings
    registry: Any
    authenticator: Any
    audit_log: Any
    gateway_service: Any


_container: GatewayContainer | None = None


def build_container(settings: GatewaySettings) -> GatewayContainer:
    from gateway.services.auth import ApiKeyAuthenticator
    from gateway.services.gateway import GatewayService
    from gateway.services.observability import AuditLog
    from gateway.services.registry import RouteRegistry

    registry = RouteRegistry(settings.upstreams)
    authenticator = ApiKeyAuthenticator(settings.admin_api_key)
    audit_log = AuditLog(max_events=20)
    gateway_service = GatewayService(registry=registry, audit_log=audit_log)
    return GatewayContainer(
        settings=settings,
        registry=registry,
        authenticator=authenticator,
        audit_log=audit_log,
        gateway_service=gateway_service,
    )


def set_container(container: GatewayContainer) -> None:
    global _container
    _container = container


def get_container() -> GatewayContainer:
    if _container is None:
        raise RuntimeError("Gateway container is not initialized.")
    return _container
