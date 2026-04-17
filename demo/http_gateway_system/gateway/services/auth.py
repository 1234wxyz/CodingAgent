"""Authentication helpers for the demo gateway."""

from __future__ import annotations


class ApiKeyAuthenticator:
    def __init__(self, admin_api_key: str) -> None:
        self._admin_api_key = admin_api_key

    def authenticate(self, provided_key: str | None) -> str:
        if provided_key != self._admin_api_key:
            raise PermissionError("Missing or invalid x-api-key header.")
        return "demo-admin"
