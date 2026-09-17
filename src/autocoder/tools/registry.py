"""Controlled tool layer (spec sections 10, 26, 32).

The LLM never gets unrestricted execution. It emits structured tool calls that
are dispatched here; every call is classified, sandboxed, and audited.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..config import Config
from ..models import ToolResult
from .dev import DevTools
from .filesystem import FileSystemTools
from .git_tools import GitTools
from .inspection import InspectionTools
from .terminal import TerminalTools


class ToolRegistry:
    """Registers callable tools and dispatches structured tool calls."""

    def __init__(self, config: Config,
                 confirm: Optional[Callable[[str, str], bool]] = None,
                 audit: Optional[Callable[[str, Dict[str, Any], ToolResult], None]] = None):
        ws = Path(config.workspace)
        ws.mkdir(parents=True, exist_ok=True)
        self.fs = FileSystemTools(ws)
        self.terminal = TerminalTools(
            ws, timeout=config.command_timeout,
            require_confirmation=config.require_confirmation, confirm=confirm,
        )
        self.dev = DevTools(self.terminal)
        self.git = GitTools(self.terminal, ws)
        self.inspect = InspectionTools()
        self._audit = audit
        self._tools: Dict[str, Callable[..., ToolResult]] = {
            # filesystem
            "list_files": self.fs.list_files,
            "read_file": self.fs.read_file,
            "write_file": self.fs.write_file,
            "edit_file": self.fs.edit_file,
            "delete_file": self.fs.delete_file,
            "create_directory": self.fs.create_directory,
            "search_code": self.fs.search_code,
            # terminal
            "run_command": self.terminal.run_command,
            "run_process": self.terminal.run_process,
            "get_process_status": self.terminal.get_process_status,
            "stop_process": self.terminal.stop_process,
            # dev
            "install_dependency": self.dev.install_dependency,
            "run_build": self.dev.run_build,
            "run_tests": self.dev.run_tests,
            "run_linter": self.dev.run_linter,
            "run_formatter": self.dev.run_formatter,
            # git
            "git_status": self.git.git_status,
            "git_diff": self.git.git_diff,
            "git_log": self.git.git_log,
            "git_create_branch": self.git.git_create_branch,
            "git_commit": self.git.git_commit,
            # inspection
            "check_port": self.inspect.check_port,
            "health_check": self.inspect.health_check,
            "read_logs": self.inspect.read_logs,
        }

    def names(self) -> List[str]:
        return sorted(self._tools)

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        fn = self._tools.get(name)
        if fn is None:
            res = ToolResult(ok=False, error=f"unknown tool: {name}")
        else:
            try:
                res = fn(**kwargs)
            except TypeError as e:
                res = ToolResult(ok=False, error=f"bad arguments for {name}: {e}")
            except Exception as e:  # tools must never crash the loop
                res = ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
        if self._audit:
            try:
                self._audit(name, kwargs, res)
            except Exception:
                pass
        return res
