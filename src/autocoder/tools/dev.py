"""Development tools: dependency install, build, tests, lint (spec section 10)."""
from __future__ import annotations

from ..models import ToolResult
from .terminal import TerminalTools


class DevTools:
    """Thin, language-aware wrappers over the terminal."""

    def __init__(self, terminal: TerminalTools):
        self.terminal = terminal

    def install_dependency(self, spec: str, manager: str = "pip") -> ToolResult:
        cmd = {
            "pip": f"python -m pip install {spec}",
            "npm": f"npm install {spec}",
            "yarn": f"yarn add {spec}",
        }.get(manager)
        if not cmd:
            return ToolResult(ok=False, error=f"unknown package manager: {manager}")
        return self.terminal.run_command(cmd, timeout=600)

    def run_build(self, command: str) -> ToolResult:
        return self.terminal.run_command(command, timeout=600)

    def run_tests(self, command: str = "python -m pytest -q") -> ToolResult:
        return self.terminal.run_command(command, timeout=600)

    def run_linter(self, command: str) -> ToolResult:
        return self.terminal.run_command(command)

    def run_formatter(self, command: str) -> ToolResult:
        return self.terminal.run_command(command)
