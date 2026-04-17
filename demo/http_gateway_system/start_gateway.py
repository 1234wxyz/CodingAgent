"""Startup entrypoint for the demo FastAPI gateway.

Default behavior is a startup check that imports and builds the app, then exits.
Use `python start_gateway.py --serve` to run the actual uvicorn server.
"""

from __future__ import annotations

import sys

import uvicorn
from uvicorn.importer import import_from_string


def startup_check() -> None:
    factory = import_from_string("gateway.app:create_app")
    app = factory()
    if app is None:
        raise RuntimeError("Application factory returned None.")
    print("Gateway startup check passed.")


def serve() -> None:
    uvicorn.run(
        "gateway.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8011,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        startup_check()
