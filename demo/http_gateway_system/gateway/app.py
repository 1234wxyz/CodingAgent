"""FastAPI application factory for the HTTP gateway demo."""

from fastapi import FastAPI

from gateway.config import load_settings
from gateway.container import build_container, set_container
from gateway.middleware import RequestIdMiddleware
from gateway.routes.admin import router as admin_router
from gateway.routes.health import router as health_router
from gateway.routes.proxy import router as proxy_router


def create_app() -> FastAPI:
    settings = load_settings()
    container = build_container(settings)
    set_container(container)

    app = FastAPI(
        title="Interview HTTP Gateway",
        version="0.1.0",
        description="Demo gateway used to showcase agent-led debugging.",
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(proxy_router)
    return app
