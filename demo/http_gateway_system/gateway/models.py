"""Pydantic models for the HTTP gateway demo."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UpstreamDefinition(BaseModel):
    service: str
    path_prefix: str
    owner: str
    timeout_ms: int = 1000
    strip_prefix: bool = True
    mock_response: dict[str, Any] = Field(default_factory=dict)


class GatewaySettings(BaseModel):
    gateway_name: str = "interview-gateway"
    environment: str = "demo"
    admin_api_key: str = "interview-demo-key"
    upstreams: list[UpstreamDefinition] = Field(default_factory=list)


class ProxyRequest(BaseModel):
    path: str = "/"
    method: str = "GET"
    payload: dict[str, Any] = Field(default_factory=dict)


class ProxyResponse(BaseModel):
    service: str
    upstream_path: str
    owner: str
    trace_id: str
    payload: dict[str, Any]


class RouteSummary(BaseModel):
    service: str
    path_prefix: str
    owner: str
    timeout_ms: int
