"""Filesystem tools (spec section 10). All access is workspace-sandboxed."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import List, Optional

from ..models import ToolResult
from .safety import resolve_in_workspace

_IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                ".mypy_cache", ".pytest_cache", "dist", "build", ".autocoder"}


class FileSystemTools:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()

    def list_files(self, subdir: str = ".", max_entries: int = 500) -> ToolResult:
        try:
            root = resolve_in_workspace(self.workspace, subdir)
        except PermissionError as e:
            return ToolResult(ok=False, error=str(e))
        if not root.exists():
            return ToolResult(ok=False, error=f"no such directory: {subdir}")
        entries: List[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
            for f in filenames:
                rel = os.path.relpath(os.path.join(dirpath, f), self.workspace)
                entries.append(rel)
                if len(entries) >= max_entries:
                    break
            if len(entries) >= max_entries:
                break
        entries.sort()
        return ToolResult(ok=True, output="\n".join(entries),
                          data={"files": entries, "count": len(entries)})

    def read_file(self, path: str, max_bytes: int = 200_000) -> ToolResult:
        try:
            p = resolve_in_workspace(self.workspace, path)
        except PermissionError as e:
            return ToolResult(ok=False, error=str(e))
        if not p.exists() or not p.is_file():
            return ToolResult(ok=False, error=f"no such file: {path}")
        try:
            content = p.read_text(encoding="utf-8", errors="replace")[:max_bytes]
        except OSError as e:
            return ToolResult(ok=False, error=str(e))
        return ToolResult(ok=True, output=content, data={"path": path})

    def write_file(self, path: str, content: str) -> ToolResult:
        try:
            p = resolve_in_workspace(self.workspace, path)
        except PermissionError as e:
            return ToolResult(ok=False, error=str(e))
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(content, encoding="utf-8")
        except OSError as e:
            return ToolResult(ok=False, error=str(e))
        action = "modified" if existed else "created"
        return ToolResult(ok=True, output=f"{action} {path} ({len(content)} bytes)",
                          data={"path": path, "action": action})

    def edit_file(self, path: str, old: str, new: str) -> ToolResult:
        """Targeted replacement — never overwrite blindly (spec section 12)."""
        res = self.read_file(path)
        if not res.ok:
            return res
        if old not in res.output:
            return ToolResult(ok=False, error="old string not found in file")
        if res.output.count(old) > 1:
            return ToolResult(ok=False, error="old string is not unique")
        return self.write_file(path, res.output.replace(old, new, 1))

    def delete_file(self, path: str) -> ToolResult:
        try:
            p = resolve_in_workspace(self.workspace, path)
        except PermissionError as e:
            return ToolResult(ok=False, error=str(e))
        if not p.exists():
            return ToolResult(ok=False, error=f"no such file: {path}")
        try:
            p.unlink()
        except OSError as e:
            return ToolResult(ok=False, error=str(e))
        return ToolResult(ok=True, output=f"deleted {path}",
                          data={"path": path, "action": "deleted"})

    def create_directory(self, path: str) -> ToolResult:
        try:
            p = resolve_in_workspace(self.workspace, path)
        except PermissionError as e:
            return ToolResult(ok=False, error=str(e))
        p.mkdir(parents=True, exist_ok=True)
        return ToolResult(ok=True, output=f"created directory {path}")

    def search_code(self, pattern: str, glob: str = "*",
                    max_results: int = 100) -> ToolResult:
        """Substring search across text files (spec sections 10, 13)."""
        hits: List[str] = []
        for dirpath, dirnames, filenames in os.walk(self.workspace):
            dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
            for f in filenames:
                if not fnmatch.fnmatch(f, glob):
                    continue
                fp = Path(dirpath) / f
                try:
                    for i, line in enumerate(
                        fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                    ):
                        if pattern in line:
                            rel = os.path.relpath(fp, self.workspace)
                            hits.append(f"{rel}:{i}: {line.strip()[:200]}")
                            if len(hits) >= max_results:
                                break
                except OSError:
                    continue
                if len(hits) >= max_results:
                    break
            if len(hits) >= max_results:
                break
        return ToolResult(ok=True, output="\n".join(hits),
                          data={"hits": hits, "count": len(hits)})
