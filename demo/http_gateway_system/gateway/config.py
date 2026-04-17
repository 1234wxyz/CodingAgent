"""Configuration loader for the HTTP gateway demo."""

from __future__ import annotations

import json
from pathlib import Path

from gateway.models import GatewaySettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "upstreams.json"


def load_settings() -> GatewaySettings:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return GatewaySettings.model_validate(payload)
