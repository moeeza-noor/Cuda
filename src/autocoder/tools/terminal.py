"""Terminal / process tools with safety gating (spec sections 10, 11, 20)."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from ..models import Risk, ToolResult
from .safety import classify_command, redact_secrets


class TerminalTools:
    def __init__(self, workspace: Path, timeout: int = 120,
                 require_confirmation: bool = True,
                 confirm: Optional[Callable[[str, str], bool]] = None):
        self.workspace = Path(workspace).resolve()
        self.timeout = timeout
        self.require_confirmation = require_confirmation
        # confirm(command, reason) -> bool. Default denies (autonomous-safe).
        self.confirm = confirm or (lambda cmd, reason: False)
        self._procs: Dict[str, subprocess.Popen] = {}

    def run_command(self, command: str, timeout: Optional[int] = None,
                    env: Optional[dict] = None) -> ToolResult:
        risk, reason = classify_command(command)
        if risk == Risk.BLOCKED:
            return ToolResult(ok=False, error=f"BLOCKED: {reason}",
                              data={"risk": risk.value})
        if risk == Risk.REQUIRES_CONFIRMATION and self.require_confirmation:
            if not self.confirm(command, reason):
                return ToolResult(
                    ok=False,
                    error=f"denied (requires confirmation): {reason}",
                    data={"risk": risk.value, "confirmed": False},
                )
        try:
            proc = subprocess.run(
                command, shell=True, cwd=str(self.workspace),
                capture_output=True, text=True,
                timeout=timeout or self.timeout, env=env,
            )
        except subprocess.TimeoutExpired as e:
            return ToolResult(ok=False, error=f"timeout after {e.timeout}s",
                              data={"risk": risk.value})
        out = redact_secrets((proc.stdout or "") + (proc.stderr or ""))
        return ToolResult(
            ok=proc.returncode == 0, output=out,
            error="" if proc.returncode == 0 else out[-4000:],
            exit_code=proc.returncode, data={"risk": risk.value},
        )

    def run_process(self, command: str, name: str) -> ToolResult:
        """Start a long-running background process (e.g. an app server)."""
        risk, reason = classify_command(command)
        if risk == Risk.BLOCKED:
            return ToolResult(ok=False, error=f"BLOCKED: {reason}")
        proc = subprocess.Popen(
            command, shell=True, cwd=str(self.workspace),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self._procs[name] = proc
        return ToolResult(ok=True, output=f"started {name} (pid {proc.pid})",
                          data={"pid": proc.pid, "name": name})

    def get_process_status(self, name: str) -> ToolResult:
        proc = self._procs.get(name)
        if not proc:
            return ToolResult(ok=False, error=f"no such process: {name}")
        code = proc.poll()
        status = "running" if code is None else f"exited({code})"
        return ToolResult(ok=True, output=status,
                          data={"running": code is None, "returncode": code})

    def stop_process(self, name: str) -> ToolResult:
        proc = self._procs.get(name)
        if not proc:
            return ToolResult(ok=False, error=f"no such process: {name}")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._procs.pop(name, None)
        return ToolResult(ok=True, output=f"stopped {name}")

    def stop_all(self) -> None:
        for name in list(self._procs):
            self.stop_process(name)
