"""Structured logging and an execution timeline (spec section 26)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..tools.safety import redact_secrets


class EventLog:
    """Append-only structured event log with an in-memory timeline.

    Every event is a small JSON record. Secrets are redacted before writing.
    A subscriber callback enables live UI streaming (spec section 27).
    """

    def __init__(self, path: Optional[Path] = None, echo: bool = True):
        self.path = Path(path) if path else None
        self.echo = echo
        self.timeline: List[Dict[str, Any]] = []
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        self._subscribers.append(fn)

    def emit(self, agent: str, action: str, result: str = "info",
             **fields: Any) -> Dict[str, Any]:
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent": agent,
            "action": action,
            "result": result,
        }
        for k, v in fields.items():
            if isinstance(v, str):
                v = redact_secrets(v)
            event[k] = v
        self.timeline.append(event)
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        if self.echo:
            self._print(event)
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception:
                pass
        return event

    def _print(self, event: Dict[str, Any]) -> None:
        icon = {"success": "✓", "failure": "✗",
                "info": "•", "running": "⟳"}.get(event["result"], "•")
        detail = ""
        for k in ("task_id", "file", "detail", "phase"):
            if event.get(k):
                detail += f" {event[k]}"
        sys.stdout.write(f"{icon} [{event['agent']}] {event['action']}{detail}\n")
        sys.stdout.flush()
