"""Self-review agent (spec sections 18, 32).

Combines a deterministic secret/security scan of the diff with an LLM review of
architecture and code quality.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from ..tools.registry import ToolRegistry
from .base import BaseAgent

_SYSTEM = (
    "You are a code reviewer. Assess architecture coherence, code quality, error "
    "handling, and security. Report concrete issues; approve only if none are "
    "blocking."
)

# Heuristics for a hardcoded-secret scan (spec section 32).
_SECRET_PATTERNS = [
    r"(?i)aws_secret_access_key\s*=\s*['\"][^'\"]+['\"]",
    r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9]{20,}['\"]",
    r"(?i)secret\s*=\s*['\"][A-Za-z0-9]{16,}['\"]",
    r"-----BEGIN (RSA|OPENSSH|PRIVATE) KEY-----",
    r"(?i)password\s*=\s*['\"][^'\"]{6,}['\"]",
]


class Reviewer(BaseAgent):
    name = "reviewer"

    def scan_secrets(self, tools: ToolRegistry) -> List[str]:
        findings: List[str] = []
        listing = tools.call("list_files")
        for path in listing.data.get("files", []):
            if Path(path).suffix in (".png", ".jpg", ".lock"):
                continue
            r = tools.call("read_file", path=path)
            if not r.ok:
                continue
            for pat in _SECRET_PATTERNS:
                for m in re.finditer(pat, r.output):
                    # Ignore clearly-marked development placeholders.
                    if "dev-token" in m.group(0) or "example" in m.group(0).lower():
                        continue
                    findings.append(f"{path}: possible secret ({pat[:24]}...)")
        return findings

    def review(self, tools: ToolRegistry, architecture: Dict[str, Any]) -> Dict[str, Any]:
        self.log.emit(self.name, "review", "running")
        secrets = self.scan_secrets(tools)
        result = self._structured(
            f"Architecture:\n{architecture}\n\nReview the implemented code for "
            f"quality, security and correctness.",
            kind="review", model=self.config.strong_model, system=_SYSTEM,
            schema_hint='{"issues": [], "security": [], "summary": "", '
                        '"approved": true}',
        )
        result.setdefault("security", [])
        result["security"].extend(secrets)
        if secrets:
            result["approved"] = False
        self.log.emit(
            self.name, "review complete",
            "success" if result.get("approved") else "failure",
            detail=f"{len(result.get('issues', []))} issues, "
                   f"{len(result.get('security', []))} security findings",
        )
        return result

    def apply_fixes(self, issues: List[str], tools: ToolRegistry) -> List[str]:
        """Ask the model for targeted fixes to reported code issues.

        Mirrors the debugger's apply step: minimal, targeted file writes/edits.
        Security-secret findings are surfaced, not auto-patched, since blindly
        rewriting a suspected secret is riskier than reporting it.
        """
        if not issues:
            return []
        listing = tools.call("list_files")
        files = [f for f in listing.data.get("files", [])
                 if f.endswith((".py", ".js", ".ts"))][:20]
        file_ctx = []
        for path in files:
            r = tools.call("read_file", path=path)
            if r.ok:
                file_ctx.append(f"--- {path} ---\n{r.output}")
            file_ctx.append(f"[[FILE:{path}]]")
        plan = self._structured(
            "Fix these review findings with minimal, targeted changes:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n\nRelevant files:\n" + "\n".join(file_ctx),
            kind="review_fix", model=self.config.strong_model, system=_SYSTEM,
            schema_hint='{"files": [{"path": "", "action": "write|edit", '
                        '"content": "", "old": "", "new": ""}], "commands": []}',
        )
        applied: List[str] = []
        for f in plan.get("files", []):
            path = f.get("path")
            if not path:
                continue
            if f.get("action") == "edit" and f.get("old"):
                res = tools.call("edit_file", path=path, old=f["old"],
                                 new=f.get("new", ""))
            else:
                res = tools.call("write_file", path=path, content=f.get("content", ""))
            if res.ok:
                applied.append(path)
        if applied:
            self.log.emit(self.name, "review fixes applied", "success",
                          detail=",".join(applied))
        return applied
