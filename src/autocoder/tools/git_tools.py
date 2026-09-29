"""Git tools (spec section 23). Never commits .env / secrets."""
from __future__ import annotations

from pathlib import Path

from ..models import ToolResult
from .terminal import TerminalTools

_NEVER_COMMIT = {".env", ".env.local", "id_rsa", "credentials.json"}


class GitTools:
    def __init__(self, terminal: TerminalTools, workspace: Path):
        self.terminal = terminal
        self.workspace = Path(workspace).resolve()

    def git_status(self) -> ToolResult:
        return self.terminal.run_command("git status --porcelain=v1 -b")

    def git_diff(self, staged: bool = False) -> ToolResult:
        return self.terminal.run_command(
            "git diff --stat" + (" --cached" if staged else "")
        )

    def git_log(self, n: int = 10) -> ToolResult:
        return self.terminal.run_command(f"git log --oneline -{n}")

    def git_create_branch(self, name: str) -> ToolResult:
        return self.terminal.run_command(f"git checkout -B {name}")

    def _guard_secrets(self) -> ToolResult:
        for name in _NEVER_COMMIT:
            if (self.workspace / name).exists():
                # Ensure it is ignored, not staged.
                self.terminal.run_command(f"git reset -q -- {name}")
        return ToolResult(ok=True)

    def git_commit(self, message: str, add_all: bool = True) -> ToolResult:
        if add_all:
            self.terminal.run_command("git add -A")
        self._guard_secrets()
        # Use a file-free commit message via -m; shell-escape naively.
        safe = message.replace('"', '\\"')
        return self.terminal.run_command(f'git commit -m "{safe}"')
