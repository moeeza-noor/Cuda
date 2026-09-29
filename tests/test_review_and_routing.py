"""Tests for cost routing, milestone commits, and the reviewer feedback loop."""
import subprocess

from autocoder.config import Config
from autocoder.core.orchestrator import Orchestrator
from autocoder.llm.mock_provider import MockProvider


def _run(tmp_path, provider=None):
    config = Config(workspace=tmp_path, provider="mock",
                    require_confirmation=False)
    orch = Orchestrator(config, llm=provider)
    report = orch.run("Build a task management REST API with auth and CRUD.")
    return orch, report


def test_cost_routing_uses_fast_model_for_analysis(tmp_path):
    provider = MockProvider()
    orch, _ = _run(tmp_path, provider)
    calls = dict()  # kind -> model (last seen)
    for kind, model in provider.calls:
        calls.setdefault(kind, model)
    # Requirement analysis runs on the fast model...
    assert calls["requirement_analysis"] == orch.config.fast_model
    # ...while architecture and coding stay on the strong model.
    assert calls["architecture"] == orch.config.strong_model
    assert calls["coding"] == orch.config.strong_model


def test_milestone_commits_created(tmp_path):
    _run(tmp_path)
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path,
                         capture_output=True, text=True)
    assert log.returncode == 0
    lines = [l for l in log.stdout.splitlines() if l.strip()]
    # A plan commit plus a commit per completed task -> several commits.
    # (The self-review commit no-ops when the tree is already clean.)
    assert len(lines) >= 3, log.stdout
    assert any("plan" in l for l in lines)
    assert any("feat:" in l for l in lines)


class _ReviewLoopProvider(MockProvider):
    """Reports one fixable issue on the first review, then approves."""

    def __init__(self):
        super().__init__()
        self._reviews = 0
        self._fixed = False

    def _k_review(self, prompt):
        self._reviews += 1
        if self._reviews == 1:
            return {"issues": ["missing docstring in app/store.py"],
                    "security": [], "summary": "one nit", "approved": False}
        return {"issues": [], "security": [], "summary": "clean",
                "approved": True}

    def _k_review_fix(self, prompt):
        self._fixed = True
        return {"files": [{"path": "REVIEW_NOTE.md", "action": "write",
                           "content": "# addressed review nit\n"}],
                "commands": []}


def test_reviewer_loop_fixes_then_approves(tmp_path):
    provider = _ReviewLoopProvider()
    orch, _ = _run(tmp_path, provider)
    # The loop applied a fix and re-reviewed to approval.
    assert provider._fixed is True
    assert provider._reviews >= 2
    review = orch.memory.recall("review")
    assert review["approved"] is True
    assert (tmp_path / "REVIEW_NOTE.md").exists()
