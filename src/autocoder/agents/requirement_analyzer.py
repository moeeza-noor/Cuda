"""Requirement Analyzer (spec section 4)."""
from __future__ import annotations

from ..models import RequirementSpec
from .base import BaseAgent

_SYSTEM = (
    "You are a requirements analyst. Convert a natural-language application "
    "requirement into a structured specification. Separate explicit requirements "
    "from implied requirements and from assumptions you had to make. Assumptions "
    "must never be silently promoted to requirements."
)

_SCHEMA = """{
  "project_name": "", "description": "",
  "objectives": [], "functional_requirements": [], "non_functional_requirements": [],
  "users": [], "roles": [], "features": [], "integrations": [], "constraints": [],
  "technology_preferences": [], "acceptance_criteria": [],
  "implied_requirements": [], "assumptions": []
}"""


class RequirementAnalyzer(BaseAgent):
    name = "requirement_analyzer"

    def analyze(self, requirement: str) -> RequirementSpec:
        self.log.emit(self.name, "analyze requirement", "running")
        data = self._structured(
            f"Requirement:\n{requirement}",
            kind="requirement_analysis",
            model=self.config.strong_model,
            system=_SYSTEM,
            schema_hint=_SCHEMA,
        )
        spec = RequirementSpec.from_dict(data)
        if not spec.project_name:
            spec.project_name = "app"
        self.log.emit(
            self.name, "requirement analyzed", "success",
            detail=f"{len(spec.functional_requirements)} functional reqs, "
                   f"{len(spec.acceptance_criteria)} acceptance criteria, "
                   f"{len(spec.assumptions)} assumptions",
        )
        return spec
