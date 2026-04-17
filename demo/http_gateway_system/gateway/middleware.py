"""Middleware used by the demo gateway."""

from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.request_id = request.headers.get(
            "x-request-id",
            f"req-{uuid4().hex[:10]}",
        )
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response
