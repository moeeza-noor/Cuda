"""Testing agent (spec section 15).

Runs real tests (never claims a pass without executing) and interprets the
output. Determines an appropriate test command from the workspace when one is
not supplied.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import TestReport
from ..tools.registry import ToolRegistry
from .base import BaseAgent


class TestAgent(BaseAgent):
    name = "test_agent"

    def detect_command(self, tools: ToolRegistry) -> Optional[str]:
        ws = Path(tools.fs.workspace)
        if (ws / "tests").exists() or list(ws.glob("test_*.py")) or list(
            ws.glob("tests/test_*.py")
        ):
            return "python -m pytest -q"
        if (ws / "package.json").exists():
            pkg = tools.call("read_file", path="package.json")
            if pkg.ok and '"test"' in pkg.output:
                return "npm test --silent"
        return None

    def run(self, tools: ToolRegistry, command: Optional[str] = None) -> TestReport:
        cmd = command or self.detect_command(tools)
        if not cmd:
            self.log.emit(self.name, "no tests found", "info")
            return TestReport(passed=True, summary="no tests to run")
        self.log.emit(self.name, "run tests", "running", detail=cmd)
        res = tools.call("run_tests", command=cmd)
        report = TestReport(
            passed=res.ok,
            summary=("tests passed" if res.ok else "tests failed"),
            raw_output=res.output,
        )
        if not res.ok:
            report.failures = self._extract_failures(res.output)
        self.log.emit(
            self.name, "tests complete",
            "success" if res.ok else "failure",
            detail=report.summary,
        )
        return report

    @staticmethod
    def _extract_failures(output: str) -> list:
        failures = []
        for line in (output or "").splitlines():
            s = line.strip()
            if s.startswith("FAILED ") or s.startswith("ERROR ") or \
               "assert" in s.lower() and "Error" in s:
                failures.append(s[:300])
        return failures[:20]
