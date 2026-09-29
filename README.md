# autocoder — an autonomous software-engineering agent

`autocoder` takes a natural-language application requirement and autonomously
turns it into working, tested software inside a workspace. It is not a chatbot
that prints code — it is a **software-engineering agent** with planning, tool
execution, verification, memory, iteration and recovery.

It never assumes generated code works. A task is complete only when there is
**evidence** (executed tests + verified acceptance criteria).

```
UNDERSTAND → INSPECT → PLAN → IMPLEMENT → RUN → TEST → OBSERVE
          → DEBUG → VERIFY → ITERATE → COMPLETE
```

## Quick start

No third-party dependencies are required for the core loop — it ships with a
deterministic **offline provider** so you can run the whole thing immediately.

```bash
# from the repo root
export PYTHONPATH=src

# Build an app into a fresh workspace (offline, deterministic provider):
python -m autocoder.cli -w ./workspace \
  "Build a task management REST API with authentication, CRUD and reporting."

# Or launch the developer web UI (three-panel: project / activity / task + terminal):
python -m autocoder.cli --serve --port 8080 -w ./workspace
```

The agent analyzes the requirement, inspects the workspace, plans tasks, writes
code, runs the tests, **observes a failure, debugs it, re-tests**, verifies every
acceptance criterion, runs a self-review, and prints a final report.

Install as a package to get the `autocoder` command:

```bash
pip install -e .            # core (zero third-party deps)
pip install -e '.[dev]'     # + pytest
pip install -e '.[anthropic,openai]'   # live LLM providers
pip install -e '.[browser]'            # Playwright UI-testing agent
```

## Using a real LLM

Configure via environment (see `.env.example`). The agent is provider-agnostic
(spec §29):

```bash
export AUTOCODER_PROVIDER=anthropic          # mock | anthropic | openai | ollama
export ANTHROPIC_API_KEY=sk-ant-...
export AUTOCODER_STRONG_MODEL=claude-sonnet-5
export AUTOCODER_FAST_MODEL=claude-haiku-4-5-20251001
```

Providers implement a small interface (`generate`, `generate_structured`,
`stream`). The default `generate_structured` robustly extracts JSON from model
output, so structured decisions do not rely on fragile text parsing.

## Architecture

```
User → CLI / Web UI
          │
          ▼
     Orchestrator ── owns state, decides next step, enforces retry bounds
       ├── RequirementAnalyzer   structured spec (explicit vs implied vs assumed)
       ├── RepositoryAnalyzer    static workspace inspection
       ├── Planner (Architect)   tech selection · architecture · task plan
       ├── CodingAgent           targeted file writes/edits (never blind overwrite)
       ├── TestAgent             runs REAL tests, interprets output
       ├── Debugger              classify → root-cause → minimal fix → re-test
       ├── Reviewer              quality + deterministic secret/security scan
       ├── MemoryManager         project / task / error memory
       └── StateManager          persistent, resumable ProjectState
              │
              ▼   ToolRegistry (sandboxed, safety-classified, audited)
          Workspace
```

| Concern | Where |
|---|---|
| Central control & lifecycle | `core/orchestrator.py` |
| Explicit state machine + persistence | `core/state.py`, `models.py` (`AgentState`) |
| Project / task / error memory | `core/memory.py` |
| Bounded context building | `core/context.py` |
| Structured events + timeline | `core/logging_utils.py` |
| Tool layer (fs, terminal, dev, git, inspect) | `tools/` |
| Command safety + path sandbox + redaction | `tools/safety.py` |
| LLM abstraction + providers | `llm/` |
| Specialized agents | `agents/` |
| Developer web UI (stdlib SSE) | `ui/` |

### Safety (spec §11, §32)

- Every shell command is classified **SAFE / REQUIRES_CONFIRMATION / BLOCKED**.
  Destructive commands (`rm -rf /`, `mkfs`, `curl | sh`, …) are blocked outright;
  sensitive ones (`pip install`, `git push`, `sudo`, `drop table`) require
  confirmation.
- All filesystem access is **sandboxed to the workspace** (path-traversal is
  rejected).
- Secrets are **redacted** before logging; `.env` and key files are never
  committed.

### Memory & recovery (spec §14, §17, §33)

- Error memory records `error / file / command / attempt / solution / result`
  and detects a **repeated identical failure** so the agent changes strategy
  instead of retrying the same fix.
- Retries are bounded (`MAX_ATTEMPTS_PER_TASK`, `MAX_DEBUG_ITERATIONS`).
- State is persisted to `.autocoder/state.json`; re-run with `--resume` to
  continue from the last incomplete task after an interruption.

## Tests

```bash
PYTHONPATH=src python -m pytest -q
```

The suite includes a **full end-to-end test** (`test_orchestrator_e2e.py`) that
runs the entire autonomous loop offline: it builds a real app, hits a seeded bug,
recovers via the debug loop, and independently re-runs the generated app's own
tests to confirm they pass.

## How the offline provider keeps the loop honest

The `mock` provider is deterministic and needs no network, but it does **not**
short-circuit the loop. It answers the same tagged, structured prompts any
provider gets, and deliberately ships one real bug on the first coding pass — so
the OBSERVE → DEBUG → RE-TEST cycle is genuinely exercised on every run, not
faked. Swap in a live provider and the same orchestration drives it.

## Browser / UI testing (§21)

With the `browser` extra installed, the tool layer exposes real Chromium
automation (`browser_navigate`, `browser_click`, `browser_type`, `browser_text`,
`browser_screenshot`, `browser_console_errors`) so the agent can verify *actual
user workflows*, not just that files compile. The import is guarded — a bare
install runs fine and the tools report unavailability instead of raising.
`tests/test_browser.py` drives the shipped developer UI with a real headless
browser and skips cleanly when the extra is absent.

## Self-review feedback loop (§18)

The reviewer doesn't just report — the orchestrator acts on findings in a
bounded loop mirroring the debug loop: reported issues are fed back for a
targeted fix, tests are re-run to prove the fix is sound, and the code is
re-reviewed until it approves or no fixable issues remain. Suspected secrets are
surfaced, never auto-patched.

## Cost routing (§31)

Structured extraction (requirement analysis) runs on `AUTOCODER_FAST_MODEL`;
architecture, planning, coding, debugging and review run on
`AUTOCODER_STRONG_MODEL`.

## Milestone commits (§23)

The orchestrator commits at each milestone (plan, each completed task, the
self-review pass) with descriptive messages, in a workspace it git-initializes
if needed. Secrets and `.env` are never committed.

## Limitations

- The bundled offline demo targets a Python/stdlib REST API so it runs anywhere
  with zero dependencies; richer stacks (React/FastAPI/Postgres) are driven by a
  live provider through the same orchestration and tool layer.
- A dedicated database agent (migrations / seed / schema-inspect) is not yet its
  own subsystem; DB work currently flows through the generic terminal/dev tools.
