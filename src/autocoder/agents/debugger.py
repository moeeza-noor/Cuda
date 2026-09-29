"""Autonomous debugger (spec sections 16, 17).

Reasons from actual error output, classifies the error, proposes and applies a
targeted fix, and records the attempt in error memory so the same failed fix is
not tried twice.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..core.memory import MemoryManager
from ..models import ErrorRecord, Task
from ..tools.registry import ToolRegistry
from .base import BaseAgent

_CATEGORIES = [
    ("SyntaxError", r"SyntaxError|IndentationError"),
    ("ImportError", r"ModuleNotFoundError|ImportError"),
    ("TypeError", r"TypeError"),
    ("AssertionError", r"AssertionError|assert "),
    ("DependencyError", r"No matching distribution|could not find a version"),
    ("ConfigurationError", r"ConfigError|Missing environment"),
    ("DatabaseError", r"OperationalError|IntegrityError|database"),
    ("ConnectionError", r"ConnectionRefused|Connection refused|URLError"),
    ("RuntimeError", r"RuntimeError|Traceback"),
]

_SYSTEM = (
    "You are a debugging specialist. Reason strictly from the provided error "
    "output. Identify the root cause and return a minimal, targeted fix. Do not "
    "rewrite large portions of the application."
)


class Debugger(BaseAgent):
    name = "debugger"

    def classify(self, output: str) -> str:
        for label, pat in _CATEGORIES:
            if re.search(pat, output or ""):
                return "TestFailure" if label == "AssertionError" else label
        return "TestFailure"

    def diagnose_and_fix(self, task: Task, error_output: str,
                         tools: ToolRegistry, memory: MemoryManager,
                         attempt: int) -> Dict[str, Any]:
        category = self.classify(error_output)
        record = ErrorRecord(
            error=error_output[:2000], category=category,
            file=task.files[0] if task.files else "", attempt=attempt,
        )

        prior = memory.prior_solutions(record)
        self.log.emit(self.name, "diagnose", "running", task_id=task.id,
                      detail=f"category={category}, attempt={attempt}")

        avoid = ""
        if prior:
            avoid = ("\nThese previous fixes did NOT work; try a different "
                     "approach:\n" + "\n".join(f"- {p}" for p in prior))

        # Provide the current contents of the task's files for targeted edits.
        file_ctx = []
        for path in task.files:
            r = tools.call("read_file", path=path)
            if r.ok:
                file_ctx.append(f"--- {path} ---\n{r.output}")
            file_ctx.append(f"[[FILE:{path}]]")

        prompt = (
            f"[[TASK:{task.id}]]\nTask: {task.title}\n"
            f"Error output:\n{error_output[:4000]}\n\n"
            f"Relevant files:\n" + "\n".join(file_ctx) + avoid
        )
        fix = self._structured(
            prompt, kind="debug", model=self.config.strong_model, system=_SYSTEM,
            schema_hint='{"category": "", "root_cause": "", "files": '
                        '[{"path": "", "action": "write|edit", "content": ""}], '
                        '"commands": [], "confidence": 0.0}',
        )

        applied = self._apply_fix(fix, tools)
        record.solution = fix.get("root_cause", "") + " | " + ",".join(applied)
        record.result = "applied" if applied else "no-op"
        memory.record_error(record)

        self.log.emit(self.name, "fix applied",
                      "success" if applied else "failure", task_id=task.id,
                      detail=fix.get("root_cause", "")[:120])
        fix["applied"] = applied
        return fix

    def _apply_fix(self, fix: Dict[str, Any], tools: ToolRegistry) -> List[str]:
        applied: List[str] = []
        for f in fix.get("files", []):
            path = f.get("path")
            action = f.get("action", "write")
            if not path:
                continue
            if action == "edit" and f.get("old"):
                res = tools.call("edit_file", path=path, old=f["old"],
                                 new=f.get("new", ""))
            else:
                res = tools.call("write_file", path=path, content=f.get("content", ""))
            if res.ok:
                applied.append(path)
        for cmd in fix.get("commands", []):
            tools.call("run_command", command=cmd)
        return applied
