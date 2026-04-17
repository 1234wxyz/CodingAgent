"""In-memory observability helpers for the demo gateway."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class AuditEvent:
    trace_id: str
    service: str
    actor: str
    action: str
    created_at: str


class AuditLog:
    def __init__(self, max_events: int = 20) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=max_events)

    def record(self, trace_id: str, service: str, actor: str, action: str) -> None:
        self._events.appendleft(
            AuditEvent(
                trace_id=trace_id,
                service=service,
                actor=actor,
                action=action,
                created_at=datetime.now(UTC).isoformat(),
            )
        )

    def recent(self, limit: int = 10) -> list[dict]:
        events = list(self._events)[:limit]
        return [
            {
                "trace_id": event.trace_id,
                "service": event.service,
                "actor": event.actor,
                "action": event.action,
                "created_at": event.created_at,
            }
            for event in events
        ]
