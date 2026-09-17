"""Architect + Planning engine (spec sections 6, 7, 8)."""
from __future__ import annotations

from typing import Any, Dict, List

from ..models import RepoSummary, RequirementSpec, Task
from .base import BaseAgent

_TECH_SYSTEM = (
    "You are a software architect. Given a requirement spec and workspace "
    "summary, select a small, coherent technology stack. Prefer an existing "
    "stack when the workspace already has one. Justify the choice briefly and "
    "avoid unnecessary technologies."
)

_PLAN_SYSTEM = (
    "You are a delivery planner. Produce an ordered list of small, verifiable "
    "tasks grouped into phases (Foundation, Core Features, Testing, Validation). "
    "Every task lists the files it touches and its acceptance criteria."
)


class Planner(BaseAgent):
    name = "planner"

    def select_tech(self, spec: RequirementSpec, repo: RepoSummary) -> Dict[str, Any]:
        self.log.emit(self.name, "select technology", "running")
        stack = self._structured(
            f"Requirement spec:\n{spec.to_dict()}\n\nWorkspace:\n{repo.to_dict()}",
            kind="tech_selection",
            model=self.config.strong_model,
            system=_TECH_SYSTEM,
        )
        self.log.emit(self.name, "technology selected", "success",
                      detail=stack.get("reasoning", "")[:120])
        return stack

    def design_architecture(self, spec: RequirementSpec,
                            stack: Dict[str, Any]) -> Dict[str, Any]:
        self.log.emit(self.name, "design architecture", "running")
        arch = self._structured(
            f"Requirement spec:\n{spec.to_dict()}\n\nStack:\n{stack}",
            kind="architecture",
            model=self.config.strong_model,
        )
        self.log.emit(self.name, "architecture designed", "success",
                      detail=f"{len(arch.get('endpoints', []))} endpoints")
        return arch

    def plan(self, spec: RequirementSpec, stack: Dict[str, Any],
             arch: Dict[str, Any]) -> List[Task]:
        self.log.emit(self.name, "create plan", "running")
        data = self._structured(
            f"Requirement spec:\n{spec.to_dict()}\n\nStack:\n{stack}\n\n"
            f"Architecture:\n{arch}",
            kind="planning",
            model=self.config.strong_model,
            system=_PLAN_SYSTEM,
            schema_hint='{"tasks": [{"title": "", "phase": "", "description": "", '
                        '"files": [], "acceptance_criteria": []}]}',
        )
        tasks: List[Task] = []
        prev_id = None
        for raw in data.get("tasks", []):
            task = Task(
                title=raw.get("title", "task"),
                description=raw.get("description", ""),
                phase=raw.get("phase", ""),
                files=raw.get("files", []),
                acceptance_criteria=raw.get("acceptance_criteria", []),
            )
            # Linear dependency chain by default so execution order is stable.
            if prev_id:
                task.dependencies = [prev_id]
            tasks.append(task)
            prev_id = task.id
        self.log.emit(self.name, "plan created", "success",
                      detail=f"{len(tasks)} tasks")
        return tasks
