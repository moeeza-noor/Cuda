"""End-to-end: the autonomous loop builds, tests, debugs and verifies an app.

Uses the deterministic mock provider so the whole loop runs offline. The mock
ships a real bug on the first pass, so this test proves the OBSERVE -> DEBUG ->
RE-TEST cycle actually recovers.
"""
import subprocess
import sys
from pathlib import Path

from autocoder.config import Config
from autocoder.core.orchestrator import Orchestrator


def test_full_autonomous_build(tmp_path):
    config = Config(workspace=tmp_path, provider="mock",
                    require_confirmation=False)
    orch = Orchestrator(config)
    report = orch.run("Build a task management REST API with authentication.")

    # The agent must have produced a COMPLETED result with evidence.
    assert report["status"] == "COMPLETED", report
    assert report["tests"]["passed"] is True
    assert report["acceptance"]["met"] == report["acceptance"]["total"]
    assert report["acceptance"]["total"] > 0

    # Real files were created in the workspace.
    for f in ("app/store.py", "app/server.py", "app/main.py",
              "tests/test_store.py", "tests/test_api.py"):
        assert (tmp_path / f).exists(), f"{f} missing"

    # The debug loop actually fixed the seeded bug.
    store = (tmp_path / "app" / "store.py").read_text()
    assert "return dict(item)" in store
    assert "# BUG:" not in store

    # Independently re-run the generated app's own tests to confirm they pass.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_resume_after_state_exists(tmp_path):
    config = Config(workspace=tmp_path, provider="mock",
                    require_confirmation=False)
    Orchestrator(config).run("Build a task API.")
    # Re-run with resume: should load state and re-verify without crashing.
    report = Orchestrator(config).run("Build a task API.", resume=True)
    assert report["status"] == "COMPLETED"
