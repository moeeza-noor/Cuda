"""Memory subsystems (spec section 14).

- Project memory: durable decisions (architecture, stack, conventions).
- Task memory: completed tasks and solutions.
- Error memory: prevents repeating an identical failed fix.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import ErrorRecord


class MemoryManager:
    def __init__(self, workspace: Path):
        self.dir = Path(workspace) / ".autocoder"
        self.project_path = self.dir / "project_memory.json"
        self.error_path = self.dir / "error_memory.json"
        self.project: Dict[str, Any] = {}
        self.errors: List[ErrorRecord] = []
        self._load()

    def _load(self) -> None:
        if self.project_path.exists():
            self.project = json.loads(self.project_path.read_text(encoding="utf-8"))
        if self.error_path.exists():
            self.errors = [
                ErrorRecord.from_dict(d)
                for d in json.loads(self.error_path.read_text(encoding="utf-8"))
            ]

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.project_path.write_text(json.dumps(self.project, indent=2),
                                     encoding="utf-8")
        self.error_path.write_text(
            json.dumps([e.to_dict() for e in self.errors], indent=2),
            encoding="utf-8",
        )

    # -- project memory --------------------------------------------------- #
    def remember(self, key: str, value: Any) -> None:
        self.project[key] = value
        self._save()

    def recall(self, key: str, default: Any = None) -> Any:
        return self.project.get(key, default)

    # -- error memory ----------------------------------------------------- #
    def record_error(self, record: ErrorRecord) -> None:
        self.errors.append(record)
        self._save()

    def seen_before(self, record: ErrorRecord) -> Optional[ErrorRecord]:
        """Return a prior error with the same signature, if any.

        Used to detect a repeated failure so the agent changes strategy instead
        of retrying an identical fix (spec section 17).
        """
        sig = record.signature()
        for prior in self.errors:
            if prior.signature() == sig and prior.solution:
                return prior
        return None

    def prior_solutions(self, record: ErrorRecord) -> List[str]:
        sig = record.signature()
        return [e.solution for e in self.errors
                if e.signature() == sig and e.solution]
