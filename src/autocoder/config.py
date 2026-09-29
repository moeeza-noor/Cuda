"""Environment-driven configuration (spec sections 29, 31, 32)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (avoids a python-dotenv dependency)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Do not clobber values already present in the real environment.
        os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    provider: str = "mock"
    strong_model: str = "claude-sonnet-5"
    fast_model: str = "claude-haiku-4-5-20251001"
    workspace: Path = field(default_factory=lambda: Path.cwd())
    require_confirmation: bool = True
    command_timeout: int = 120
    max_attempts_per_task: int = 5
    max_debug_iterations: int = 5

    # Provider connection details (never printed / logged).
    anthropic_api_key: Optional[str] = None
    anthropic_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"

    @classmethod
    def load(cls, workspace: Optional[str] = None, dotenv: bool = True) -> "Config":
        if dotenv:
            _load_dotenv(Path.cwd() / ".env")
        ws = workspace or os.environ.get("AUTOCODER_WORKSPACE") or os.getcwd()
        return cls(
            provider=os.environ.get("AUTOCODER_PROVIDER", "mock").lower(),
            strong_model=os.environ.get("AUTOCODER_STRONG_MODEL", "claude-sonnet-5"),
            fast_model=os.environ.get(
                "AUTOCODER_FAST_MODEL", "claude-haiku-4-5-20251001"
            ),
            workspace=Path(ws).expanduser().resolve(),
            require_confirmation=_env_bool("AUTOCODER_REQUIRE_CONFIRMATION", True),
            command_timeout=_env_int("AUTOCODER_COMMAND_TIMEOUT", 120),
            max_attempts_per_task=_env_int("AUTOCODER_MAX_ATTEMPTS_PER_TASK", 5),
            max_debug_iterations=_env_int("AUTOCODER_MAX_DEBUG_ITERATIONS", 5),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            anthropic_base_url=os.environ.get("AUTOCODER_ANTHROPIC_BASE_URL"),
            openai_api_key=os.environ.get("OPENAI_API_KEY"),
            openai_base_url=os.environ.get("AUTOCODER_OPENAI_BASE_URL"),
            ollama_base_url=os.environ.get(
                "AUTOCODER_OLLAMA_BASE_URL", "http://localhost:11434"
            ),
        )

    def redacted(self) -> dict:
        """Config view safe to log — secrets removed (spec section 32)."""
        return {
            "provider": self.provider,
            "strong_model": self.strong_model,
            "fast_model": self.fast_model,
            "workspace": str(self.workspace),
            "require_confirmation": self.require_confirmation,
            "command_timeout": self.command_timeout,
            "max_attempts_per_task": self.max_attempts_per_task,
            "max_debug_iterations": self.max_debug_iterations,
            "anthropic_api_key": "***" if self.anthropic_api_key else None,
            "openai_api_key": "***" if self.openai_api_key else None,
        }
