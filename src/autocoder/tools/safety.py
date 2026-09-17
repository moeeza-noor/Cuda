"""Command safety classification and path sandboxing (spec sections 11, 32)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple

from ..models import Risk

# Patterns that must never run automatically.
_BLOCKED_PATTERNS = [
    r"\brm\s+-rf\s+/(?:\s|$)",        # rm -rf /
    r"\brm\s+-rf\s+~(?:\s|$)",        # rm -rf ~
    r"\brm\s+-rf\s+/\*",              # rm -rf /*
    r":\(\)\s*\{.*\};:",              # fork bomb
    r"\bmkfs\b",                       # format filesystem
    r"\bdd\b.*of=/dev/",              # overwrite raw devices
    r">\s*/dev/sd[a-z]",              # write to a disk device
    r"\bchmod\s+-R\s+777\s+/",       # weaken root perms
    r"\bshutdown\b|\breboot\b|\bhalt\b",
    r"\bcurl\b[^\n|]*\|\s*(sudo\s+)?(sh|bash)\b",  # curl | sh
    r"\bwget\b[^\n|]*\|\s*(sudo\s+)?(sh|bash)\b",
]

# Patterns that require explicit human confirmation.
_CONFIRM_PATTERNS = [
    r"\brm\s+-rf?\b",                 # any recursive/forced remove
    r"\bgit\s+push\b",               # pushing code
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bsudo\b",
    r"\bdrop\s+database\b",
    r"\bdrop\s+table\b",
    r"\btruncate\s+table\b",
    r"\bpip\s+install\b",            # installs mutate the environment
    r"\bnpm\s+install\b",
    r"\bdocker\s+(rm|rmi|system\s+prune)\b",
    r"\bkill\b|\bpkill\b",
]


def classify_command(command: str) -> Tuple[Risk, str]:
    """Classify a shell command as SAFE / REQUIRES_CONFIRMATION / BLOCKED."""
    cmd = command.strip()
    for pat in _BLOCKED_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return Risk.BLOCKED, f"matched blocked pattern: {pat}"
    for pat in _CONFIRM_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return Risk.REQUIRES_CONFIRMATION, f"matched sensitive pattern: {pat}"
    return Risk.SAFE, "no sensitive pattern matched"


def resolve_in_workspace(workspace: Path, target: str) -> Path:
    """Resolve `target` and guarantee it stays inside `workspace`.

    Raises PermissionError on path traversal outside the sandbox (spec 32).
    """
    workspace = workspace.resolve()
    p = (workspace / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
    if workspace != p and workspace not in p.parents:
        raise PermissionError(
            f"path escapes workspace sandbox: {target!r} -> {p}"
        )
    return p


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|bearer|authorization)"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})"
)


def redact_secrets(text: str) -> str:
    """Redact obvious secrets before logging (spec section 32)."""
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}=***REDACTED***", text or "")
