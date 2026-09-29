# CLAUDE.md

Guidance for working in this repository.

## What this is

`autocoder` — an autonomous software-engineering agent. It takes a
natural-language requirement and drives it to working, tested software through
the loop: understand → inspect → plan → implement → run → test → observe →
debug → verify → iterate → complete. Work is "done" only with evidence
(executed tests + verified acceptance criteria), never because code was generated.

## Layout

- `src/autocoder/` — the package (installed via `pip install -e .`).
  - `core/orchestrator.py` — the central controller; owns the lifecycle.
  - `core/state.py`, `core/memory.py`, `core/context.py`, `core/logging_utils.py`
  - `agents/` — requirement analyzer, repo analyzer, planner, coder, tester,
    debugger, reviewer (coordinated by the orchestrator; the LLM never drives
    control flow directly).
  - `tools/` — sandboxed, safety-classified, audited tool layer. `safety.py`
    holds command classification (SAFE / REQUIRES_CONFIRMATION / BLOCKED),
    path-traversal protection, and secret redaction. `browser.py` is the
    optional Playwright UI-testing agent (guarded import; `browser` extra).
  - `llm/` — provider abstraction. `mock_provider.py` is deterministic and
    offline; `factory.py` selects the provider from `Config`.
  - `ui/` — dependency-free stdlib web UI (SSE streaming).
- `tests/` — pytest suite, including a full offline end-to-end test.

## Conventions

- **Core has zero required third-party dependencies.** Keep it that way; new
  runtime deps go behind optional extras in `pyproject.toml` with guarded
  imports (see `llm/anthropic_provider.py`).
- All filesystem access is workspace-sandboxed; never bypass `resolve_in_workspace`.
- Never weaken command safety classification to make something run.
- Never log secrets; use `redact_secrets` on anything that may contain them.

## Common commands

```bash
export PYTHONPATH=src            # or `pip install -e '.[dev]'`
python -m pytest -q              # run tests (24 tests)
python -m autocoder.cli -w ./workspace "Build a task REST API with auth and CRUD."
python -m autocoder.cli --serve --port 8080 -w ./workspace   # web UI
```

## The mock provider

Tests and the default CLI use the `mock` provider (`AUTOCODER_PROVIDER=mock`).
It is deterministic and needs no network, and it deliberately ships one real bug
on the first coding pass so the debug loop is genuinely exercised. Do not "fix"
that seeded bug in the provider — the end-to-end test depends on the recovery.
