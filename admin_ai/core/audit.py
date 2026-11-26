"""Audit events for agent runs. Standard library only.

Events never contain message text, tool results or raw tool arguments (only a SHA-256 digest of the
arguments), so the log cannot become a second copy of user or catalogue data.
"""
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import List, Protocol


@dataclass(frozen=True)
class AuditEvent:
    run_id: str
    event: str
    principal_id: str
    role: str
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...


def args_digest(arguments) -> str:
    try:
        raw = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return "unhashable"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: List[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class LoggingAuditSink:
    """One JSON line per event on stdout (captured by the hosting platform's log drain)."""

    def __init__(self, name: str = "admin_ai.audit") -> None:
        self._log = logging.getLogger(name)
        if not self._log.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._log.addHandler(handler)
            self._log.setLevel(logging.INFO)
            self._log.propagate = False

    def record(self, event: AuditEvent) -> None:
        self._log.info(json.dumps({
            "audit": "admin_ai", "ts": event.ts, "run_id": event.run_id, "event": event.event,
            "principal": event.principal_id, "role": event.role, "data": event.data,
        }, default=str, sort_keys=True))
