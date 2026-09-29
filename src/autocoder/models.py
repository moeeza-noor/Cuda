"""Core data models shared across the agent.

These are plain dataclasses (no third-party deps) with JSON (de)serialization so
state and memory can be persisted to disk and reloaded after an interruption.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _now() -> float:
    return time.time()


# --------------------------------------------------------------------------- #
# Agent + task lifecycle
# --------------------------------------------------------------------------- #
class AgentState(str, Enum):
    """Explicit state machine for the orchestrator (spec section 25)."""

    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    INSPECTING = "INSPECTING"
    PLANNING = "PLANNING"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    DEBUGGING = "DEBUGGING"
    REVIEWING = "REVIEWING"
    VERIFYING = "VERIFYING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class Risk(str, Enum):
    """Command safety classification (spec section 11)."""

    SAFE = "SAFE"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    BLOCKED = "BLOCKED"


@dataclass
class Task:
    title: str
    description: str = ""
    phase: str = ""
    id: str = field(default_factory=lambda: _new_id("TASK"))
    dependencies: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    status: str = TaskStatus.PENDING.value
    attempts: int = 0
    result: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Task":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RequirementSpec:
    """Structured project specification (spec section 4)."""

    project_name: str = ""
    description: str = ""
    objectives: List[str] = field(default_factory=list)
    functional_requirements: List[str] = field(default_factory=list)
    non_functional_requirements: List[str] = field(default_factory=list)
    users: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    technology_preferences: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    # Provenance: keep explicit / implied / assumptions separate (spec section 4).
    implied_requirements: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RequirementSpec":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RepoSummary:
    """Repository / workspace analysis output (spec section 5)."""

    project_type: str = "empty"
    frontend: str = "none"
    backend: str = "none"
    database: str = "none"
    frameworks: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    package_manager: str = "none"
    testing_framework: str = "none"
    build_system: str = "none"
    existing_apis: List[str] = field(default_factory=list)
    existing_components: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    potential_risks: List[str] = field(default_factory=list)
    file_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RepoSummary":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    exit_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestReport:
    passed: bool
    summary: str = ""
    failures: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ErrorRecord:
    """Error memory entry (spec section 14)."""

    error: str
    category: str = "RuntimeError"
    file: str = ""
    line: Optional[int] = None
    command: str = ""
    attempt: int = 0
    solution: str = ""
    result: str = ""
    id: str = field(default_factory=lambda: _new_id("ERR"))
    ts: float = field(default_factory=_now)

    def signature(self) -> str:
        """A stable key used to detect repeated identical failures."""
        head = (self.error or "").strip().splitlines()
        first = head[0] if head else ""
        return f"{self.category}:{self.file}:{first[:160]}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ErrorRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class FileChange:
    path: str
    action: str  # created | modified | deleted
    ts: float = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
