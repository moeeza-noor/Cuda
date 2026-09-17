"""Repository / workspace analyzer (spec section 5).

Static, deterministic inspection of the workspace — no LLM required. Detects
languages, frameworks, package managers, tests, build and entry points so the
agent modifies an existing project rather than rebuilding it.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from ..core.logging_utils import EventLog
from ..models import RepoSummary
from ..tools.registry import ToolRegistry

_LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".go": "Go",
    ".rs": "Rust", ".java": "Java", ".rb": "Ruby", ".php": "PHP",
}


class RepositoryAnalyzer:
    name = "repository_analyzer"

    def __init__(self, tools: ToolRegistry, log: EventLog):
        self.tools = tools
        self.log = log
        self.workspace = Path(tools.fs.workspace)

    def analyze(self) -> RepoSummary:
        self.log.emit(self.name, "inspect workspace", "running")
        listing = self.tools.call("list_files")
        files: List[str] = listing.data.get("files", []) if listing.ok else []
        summary = RepoSummary(file_count=len(files))

        langs = set()
        for f in files:
            ext = Path(f).suffix
            if ext in _LANG_BY_EXT:
                langs.add(_LANG_BY_EXT[ext])
        summary.languages = sorted(langs)

        names = {Path(f).name for f in files}
        frameworks: List[str] = []

        if "package.json" in names:
            summary.package_manager = "npm"
            pkg = self.tools.call("read_file", path="package.json")
            blob = pkg.output if pkg.ok else ""
            for fw in ("react", "next", "vue", "express", "fastify", "svelte"):
                if f'"{fw}"' in blob:
                    frameworks.append(fw)
            if any(x in blob for x in ("react", "vue", "svelte", "next")):
                summary.frontend = "detected"
        if "requirements.txt" in names or "pyproject.toml" in names:
            summary.package_manager = summary.package_manager or "pip"
            for f in files:
                blob = ""
                if Path(f).name in ("requirements.txt", "pyproject.toml"):
                    r = self.tools.call("read_file", path=f)
                    blob = r.output if r.ok else ""
                for fw in ("fastapi", "flask", "django", "sqlalchemy", "pytest"):
                    if fw in blob.lower() and fw not in frameworks:
                        frameworks.append(fw)
        if "go.mod" in names:
            summary.package_manager = "go"
        if "Cargo.toml" in names:
            summary.package_manager = "cargo"

        summary.frameworks = frameworks
        if any("pytest" in fw for fw in frameworks) or any(
            "test" in Path(f).name for f in files
        ):
            summary.testing_framework = "pytest" if "Python" in langs else "detected"

        if any(Path(f).name == "docker-compose.yml" for f in files):
            summary.build_system = "docker-compose"
        elif "Dockerfile" in names:
            summary.build_system = "docker"

        for cand in ("app/main.py", "main.py", "src/index.ts", "src/index.js",
                     "manage.py", "app.py", "server.py"):
            if cand in files:
                summary.entry_points.append(cand)

        if "fastapi" in frameworks or "flask" in frameworks or "django" in frameworks:
            summary.backend = "detected"

        if not files:
            summary.project_type = "empty"
            summary.potential_risks.append(
                "Empty workspace: a full project must be scaffolded."
            )
        else:
            summary.project_type = "existing"
            if summary.testing_framework == "none":
                summary.potential_risks.append("No test framework detected.")

        self.log.emit(
            self.name, "workspace analyzed", "success",
            detail=f"type={summary.project_type}, langs={summary.languages}, "
                   f"frameworks={summary.frameworks}",
        )
        return summary
