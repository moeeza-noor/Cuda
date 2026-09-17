"""Intelligent context builder (spec sections 13, 31).

Never sends the whole repository to the model. Selects only relevant files,
task context, recent errors and architecture, keeping token usage bounded.
"""
from __future__ import annotations

from typing import List, Optional

from ..models import Task
from ..tools.registry import ToolRegistry


class ContextBuilder:
    def __init__(self, tools: ToolRegistry, max_file_bytes: int = 8000):
        self.tools = tools
        self.max_file_bytes = max_file_bytes

    def for_task(self, task: Task, architecture: dict,
                 recent_errors: Optional[List[str]] = None) -> str:
        parts: List[str] = []
        parts.append(f"# Current task [[TASK:{task.id}]]")
        parts.append(f"Title: {task.title}")
        if task.description:
            parts.append(f"Description: {task.description}")
        if task.acceptance_criteria:
            parts.append("Acceptance criteria:")
            parts.extend(f"  - {c}" for c in task.acceptance_criteria)

        if architecture:
            eps = architecture.get("endpoints")
            if eps:
                parts.append(f"Architecture endpoints: {eps}")

        # Include current contents of the files this task will touch, so the
        # coding agent modifies rather than blindly overwrites (spec section 12).
        if task.files:
            parts.append("\n# Existing file contents (for targeted edits):")
            for path in task.files:
                res = self.tools.call("read_file", path=path,
                                      max_bytes=self.max_file_bytes)
                if res.ok:
                    parts.append(f"--- {path} ---\n{res.output}")
                else:
                    parts.append(f"--- {path} (does not exist yet) ---")
            # File markers help deterministic providers route.
            for path in task.files:
                parts.append(f"[[FILE:{path}]]")

        if recent_errors:
            parts.append("\n# Recent errors to avoid repeating:")
            parts.extend(f"  - {e}" for e in recent_errors[-5:])

        return "\n".join(parts)
