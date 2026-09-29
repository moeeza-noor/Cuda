"""Persistent project + agent state (spec sections 3, 25, 33).

State is serialized to `.autocoder/state.json` so the agent can recover after an
interruption and resume from the last incomplete task instead of restarting.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import (
    AgentState,
    FileChange,
    RepoSummary,
    RequirementSpec,
    Task,
    TaskStatus,
)


@dataclass
class ProjectState:
    current_phase: str = AgentState.IDLE.value
    current_task: Optional[str] = None
    task_queue: List[Task] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    attempt_count: Dict[str, int] = field(default_factory=dict)
    test_results: List[Dict[str, Any]] = field(default_factory=list)
    file_changes: List[FileChange] = field(default_factory=list)
    architecture: Dict[str, Any] = field(default_factory=dict)
    tech_stack: Dict[str, Any] = field(default_factory=dict)
    requirements: Optional[RequirementSpec] = None
    acceptance_criteria: List[str] = field(default_factory=list)
    acceptance_status: Dict[str, bool] = field(default_factory=dict)
    user_requirement: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_phase": self.current_phase,
            "current_task": self.current_task,
            "task_queue": [t.to_dict() for t in self.task_queue],
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "attempt_count": self.attempt_count,
            "test_results": self.test_results,
            "file_changes": [c.to_dict() for c in self.file_changes],
            "architecture": self.architecture,
            "tech_stack": self.tech_stack,
            "requirements": self.requirements.to_dict() if self.requirements else None,
            "acceptance_criteria": self.acceptance_criteria,
            "acceptance_status": self.acceptance_status,
            "user_requirement": self.user_requirement,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProjectState":
        return cls(
            current_phase=d.get("current_phase", AgentState.IDLE.value),
            current_task=d.get("current_task"),
            task_queue=[Task.from_dict(t) for t in d.get("task_queue", [])],
            completed_tasks=d.get("completed_tasks", []),
            failed_tasks=d.get("failed_tasks", []),
            attempt_count=d.get("attempt_count", {}),
            test_results=d.get("test_results", []),
            file_changes=[FileChange(**c) for c in d.get("file_changes", [])],
            architecture=d.get("architecture", {}),
            tech_stack=d.get("tech_stack", {}),
            requirements=(
                RequirementSpec.from_dict(d["requirements"])
                if d.get("requirements")
                else None
            ),
            acceptance_criteria=d.get("acceptance_criteria", []),
            acceptance_status=d.get("acceptance_status", {}),
            user_requirement=d.get("user_requirement", ""),
        )


class StateManager:
    """Owns the ProjectState and its persistence."""

    def __init__(self, workspace: Path):
        self.dir = Path(workspace) / ".autocoder"
        self.path = self.dir / "state.json"
        self.state = ProjectState()

    # -- persistence ------------------------------------------------------ #
    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state.to_dict(), indent=2),
                             encoding="utf-8")

    def load(self) -> bool:
        if not self.path.exists():
            return False
        self.state = ProjectState.from_dict(
            json.loads(self.path.read_text(encoding="utf-8"))
        )
        return True

    # -- phase / task helpers -------------------------------------------- #
    def set_phase(self, phase: AgentState) -> None:
        self.state.current_phase = phase.value
        self.save()

    def next_pending_task(self) -> Optional[Task]:
        """Return the next task whose dependencies are satisfied."""
        done = set(self.state.completed_tasks)
        for task in self.state.task_queue:
            if task.status not in (TaskStatus.PENDING.value,
                                   TaskStatus.IN_PROGRESS.value):
                continue
            if all(dep in done for dep in task.dependencies):
                return task
        return None

    def record_task_result(self, task: Task, success: bool) -> None:
        if success:
            task.status = TaskStatus.DONE.value
            if task.id not in self.state.completed_tasks:
                self.state.completed_tasks.append(task.id)
        else:
            task.status = TaskStatus.FAILED.value
            if task.id not in self.state.failed_tasks:
                self.state.failed_tasks.append(task.id)
        self.save()

    def bump_attempt(self, task_id: str) -> int:
        n = self.state.attempt_count.get(task_id, 0) + 1
        self.state.attempt_count[task_id] = n
        self.save()
        return n

    def record_file_change(self, path: str, action: str) -> None:
        self.state.file_changes.append(FileChange(path=path, action=action))
        self.save()

    def all_tasks_done(self) -> bool:
        return all(
            t.status in (TaskStatus.DONE.value, TaskStatus.SKIPPED.value)
            for t in self.state.task_queue
        ) and bool(self.state.task_queue)
