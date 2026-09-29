"""Coding agent (spec section 12).

Receives project context + architecture + current task + relevant files +
acceptance criteria + previous errors, and emits structured file operations.
It inspects existing files (via the provided context) and applies targeted
writes rather than overwriting blindly.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..models import Task, ToolResult
from ..tools.registry import ToolRegistry
from .base import BaseAgent

_SYSTEM = (
    "You are a senior engineer. Implement exactly what the current task needs. "
    "Return the full desired contents of each file you create or modify. Prefer "
    "minimal, targeted changes. Do not invent files outside the task's scope."
)


class CodingAgent(BaseAgent):
    name = "coding_agent"

    def implement(self, task: Task, context: str,
                  tools: ToolRegistry) -> Dict[str, Any]:
        self.log.emit(self.name, "implement", "running", task_id=task.id,
                      detail=task.title)
        plan = self._structured(
            context,
            kind="coding",
            model=self.config.strong_model,
            system=_SYSTEM,
            schema_hint='{"reason": "", "files": [{"path": "", "action": '
                        '"write|edit|delete", "content": "", "old": "", "new": ""}], '
                        '"commands": [], "tests": [], "confidence": 0.0}',
        )
        applied = self._apply(plan, tools)
        self.log.emit(self.name, "implement done", "success", task_id=task.id,
                      detail=f"{len(applied)} file op(s)")
        plan["applied"] = applied
        return plan

    def _apply(self, plan: Dict[str, Any], tools: ToolRegistry) -> List[str]:
        applied: List[str] = []
        for f in plan.get("files", []):
            action = f.get("action", "write")
            path = f.get("path")
            if not path:
                continue
            if action in ("write", "create"):
                res = tools.call("write_file", path=path, content=f.get("content", ""))
            elif action == "edit":
                res = tools.call("edit_file", path=path,
                                 old=f.get("old", ""), new=f.get("new", ""))
            elif action == "delete":
                res = tools.call("delete_file", path=path)
            else:
                res = ToolResult(ok=False, error=f"unknown action {action}")
            if res.ok:
                applied.append(f"{action}:{path}")
                self.log.emit(self.name, action, "success", file=path)
            else:
                self.log.emit(self.name, action, "failure", file=path,
                              detail=res.error)
        return applied
