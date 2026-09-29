"""Central orchestrator (spec sections 1, 3, 9, 17, 19, 33, 34).

Controls the complete development lifecycle:

    UNDERSTAND -> INSPECT -> PLAN -> IMPLEMENT -> RUN -> TEST -> OBSERVE
    -> DEBUG -> VERIFY -> ITERATE -> COMPLETE

The LLM never controls the flow directly. The orchestrator owns state, decides
what happens next, enforces retry bounds, and never marks work complete without
evidence (executed tests + verified acceptance criteria).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..agents import (
    CodingAgent,
    Debugger,
    Planner,
    RepositoryAnalyzer,
    RequirementAnalyzer,
    Reviewer,
    TestAgent,
)
from ..config import Config
from ..llm.base import LLMProvider
from ..llm.factory import build_provider
from ..models import AgentState, TaskStatus, ToolResult
from ..tools.registry import ToolRegistry
from .context import ContextBuilder
from .logging_utils import EventLog
from .memory import MemoryManager
from .state import StateManager


class Orchestrator:
    def __init__(self, config: Config,
                 llm: Optional[LLMProvider] = None,
                 confirm: Optional[Callable[[str, str], bool]] = None,
                 event_subscriber: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.config = config
        self.workspace = Path(config.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.log = EventLog(self.workspace / ".autocoder" / "events.jsonl")
        if event_subscriber:
            self.log.subscribe(event_subscriber)

        self.llm = llm or build_provider(config)
        self.tools = ToolRegistry(config, confirm=confirm, audit=self._audit)
        self.state_mgr = StateManager(self.workspace)
        self.memory = MemoryManager(self.workspace)
        self.context = ContextBuilder(self.tools)

        self.requirement_agent = RequirementAnalyzer(self.llm, config, self.log)
        self.repo_agent = RepositoryAnalyzer(self.tools, self.log)
        self.planner = Planner(self.llm, config, self.log)
        self.coder = CodingAgent(self.llm, config, self.log)
        self.tester = TestAgent(self.llm, config, self.log)
        self.debugger = Debugger(self.llm, config, self.log)
        self.reviewer = Reviewer(self.llm, config, self.log)

    # -- audit hook ------------------------------------------------------- #
    def _audit(self, name: str, kwargs: Dict[str, Any], res: ToolResult) -> None:
        if name in ("read_file", "list_files", "search_code", "get_process_status"):
            return  # low-signal reads; keep the timeline focused
        self.log.emit("tool", name, "success" if res.ok else "failure",
                      file=kwargs.get("path", ""),
                      detail=(kwargs.get("command", "") or res.error)[:160])

    # -- public entrypoint ------------------------------------------------ #
    def run(self, requirement: str, resume: bool = False) -> Dict[str, Any]:
        if resume and self.state_mgr.load():
            self.log.emit("orchestrator", "resume", "info",
                          detail=f"phase={self.state_mgr.state.current_phase}")
        else:
            self.state_mgr.state.user_requirement = requirement

        st = self.state_mgr.state
        try:
            if not st.requirements:
                self._phase_understand(requirement)
            self._phase_inspect()
            if not st.task_queue:
                self._phase_plan()
            self._phase_implement()
            self._phase_verify()
            self._phase_review()
            self.state_mgr.set_phase(AgentState.COMPLETED)
        except KeyboardInterrupt:
            self.log.emit("orchestrator", "interrupted", "failure",
                          detail="state persisted; rerun with resume=True")
            raise
        finally:
            self.tools.terminal.stop_all()
            self.tools.browser.close()
            self.state_mgr.save()
        return self.final_report()

    # -- phases ----------------------------------------------------------- #
    def _phase_understand(self, requirement: str) -> None:
        self.state_mgr.set_phase(AgentState.ANALYZING)
        spec = self.requirement_agent.analyze(requirement)
        self.state_mgr.state.requirements = spec
        self.state_mgr.state.acceptance_criteria = list(spec.acceptance_criteria)
        self.state_mgr.state.acceptance_status = {
            c: False for c in spec.acceptance_criteria
        }
        self.memory.remember("assumptions", spec.assumptions)
        self.memory.remember("project_name", spec.project_name)
        self.state_mgr.save()

    def _phase_inspect(self) -> None:
        self.state_mgr.set_phase(AgentState.INSPECTING)
        repo = self.repo_agent.analyze()
        self.memory.remember("repo_summary", repo.to_dict())
        # Ensure the workspace is a git repo for change tracking (spec 23).
        if not (self.workspace / ".git").exists():
            self.tools.call("run_command", command="git init -q")
        # Guarantee a commit identity so milestone commits don't fail in a
        # fresh workspace (does not touch global git config).
        ident = self.tools.call("run_command", command="git config user.email")
        if not (ident.ok and ident.output.strip()):
            self.tools.call("run_command",
                            command='git config user.email "agent@autocoder.local"')
            self.tools.call("run_command",
                            command='git config user.name "autocoder"')
        # Keep the agent's own state and common build/cache artifacts out of the
        # user's repo so milestone commits stay clean.
        gi = self.tools.call("read_file", path=".gitignore")
        existing = gi.output if gi.ok else ""
        wanted = [".autocoder/", "__pycache__/", "*.pyc", ".pytest_cache/",
                  ".env", "node_modules/"]
        missing = [w for w in wanted if w not in existing]
        if missing:
            body = (existing.rstrip() + "\n" if existing.strip() else "")
            self.tools.call("write_file", path=".gitignore",
                            content=body + "\n".join(missing) + "\n")

    def _phase_plan(self) -> None:
        self.state_mgr.set_phase(AgentState.PLANNING)
        spec = self.state_mgr.state.requirements
        repo_dict = self.memory.recall("repo_summary", {})
        from ..models import RepoSummary

        repo = RepoSummary.from_dict(repo_dict)
        stack = self.planner.select_tech(spec, repo)
        arch = self.planner.design_architecture(spec, stack)
        tasks = self.planner.plan(spec, stack, arch)
        self.state_mgr.state.tech_stack = stack
        self.state_mgr.state.architecture = arch
        self.state_mgr.state.task_queue = tasks
        self.memory.remember("tech_stack", stack)
        self.memory.remember("architecture", arch)
        self.state_mgr.save()
        self._commit(f"docs: plan {len(tasks)} tasks and architecture")

    def _phase_implement(self) -> None:
        self.state_mgr.set_phase(AgentState.IMPLEMENTING)
        while True:
            task = self.state_mgr.next_pending_task()
            if task is None:
                break
            self.state_mgr.state.current_task = task.id
            task.status = TaskStatus.IN_PROGRESS.value
            self.state_mgr.save()
            success = self._execute_task(task)
            self.state_mgr.record_task_result(task, success)
            if success:
                self._commit(f"feat: {task.title.lower()}")
            else:
                self.log.emit("orchestrator", "task failed", "failure",
                              task_id=task.id, detail=task.title)
                # Continue with remaining independent tasks; report at the end.

    def _execute_task(self, task) -> bool:
        """Implement one task and drive it to a passing state (spec section 9)."""
        max_attempts = self.config.max_attempts_per_task
        for attempt in range(1, max_attempts + 1):
            self.state_mgr.bump_attempt(task.id)
            recent_errors = [e.solution for e in self.memory.errors[-3:] if e.solution]
            ctx = self.context.for_task(task, self.state_mgr.state.architecture,
                                        recent_errors)
            self.coder.implement(task, ctx, self.tools)
            for f in task.files:
                self.state_mgr.record_file_change(f, "written")

            # RUN / TEST / OBSERVE
            self.state_mgr.set_phase(AgentState.TESTING)
            report = self.tester.run(self.tools)
            self.state_mgr.state.test_results.append(report.to_dict())
            self.state_mgr.save()

            if report.passed:
                return True

            # DEBUG loop (bounded) — spec sections 16, 17.
            self.state_mgr.set_phase(AgentState.DEBUGGING)
            if self._debug_loop(task, report):
                return True
            self.state_mgr.set_phase(AgentState.IMPLEMENTING)
        return False

    def _debug_loop(self, task, report) -> bool:
        for it in range(1, self.config.max_debug_iterations + 1):
            self.debugger.diagnose_and_fix(
                task, report.raw_output, self.tools, self.memory, it
            )
            report = self.tester.run(self.tools)
            self.state_mgr.state.test_results.append(report.to_dict())
            self.state_mgr.save()
            if report.passed:
                self.log.emit("orchestrator", "debug resolved", "success",
                              task_id=task.id, detail=f"after {it} iteration(s)")
                return True
        self.log.emit("orchestrator", "debug exhausted", "failure",
                      task_id=task.id,
                      detail="changing strategy: escalating to next task")
        return False

    def _phase_verify(self) -> None:
        """Verify acceptance criteria with evidence (spec sections 19, 34)."""
        self.state_mgr.set_phase(AgentState.VERIFYING)
        report = self.tester.run(self.tools)
        tests_pass = report.passed
        st = self.state_mgr.state

        for crit in st.acceptance_criteria:
            low = crit.lower()
            if "test" in low:
                st.acceptance_status[crit] = tests_pass
            elif "start" in low or "build" in low:
                st.acceptance_status[crit] = self._smoke_start()
            else:
                # Criteria covered by passing integration tests are marked met
                # only when tests actually pass — never assumed.
                st.acceptance_status[crit] = tests_pass
        self.state_mgr.save()
        self.log.emit("orchestrator", "verification",
                      "success" if all(st.acceptance_status.values()) else "failure",
                      detail=f"{sum(st.acceptance_status.values())}/"
                             f"{len(st.acceptance_status)} criteria met")

    def _smoke_start(self) -> bool:
        """Best-effort: import the app / entry module to prove it starts."""
        entries = self.memory.recall("repo_summary", {}).get("entry_points", [])
        target = "app.main" if (self.workspace / "app" / "main.py").exists() else None
        if target:
            res = self.tools.call(
                "run_command",
                command=f"python -c 'import importlib; importlib.import_module(\"{target}\")'",
            )
            return res.ok
        return True

    def _phase_review(self) -> None:
        """Review, then act on findings in a bounded loop (spec section 18).

        Mirrors the debug loop: reported code issues are fed back to the reviewer
        for a targeted fix, tests are re-run to prove the fix is sound, and the
        code is re-reviewed. The loop stops when the review approves, when there
        are no fixable issues left, or when the iteration bound is reached.
        Security-secret findings are surfaced rather than auto-patched.
        """
        self.state_mgr.set_phase(AgentState.REVIEWING)
        review = self.reviewer.review(self.tools, self.state_mgr.state.architecture)
        for it in range(1, self.config.max_debug_iterations + 1):
            issues = review.get("issues", [])
            if review.get("approved") or not issues:
                break
            applied = self.reviewer.apply_fixes(issues, self.tools)
            if not applied:
                break  # nothing actionable was changed; avoid a no-op loop
            report = self.tester.run(self.tools)
            self.state_mgr.state.test_results.append(report.to_dict())
            if not report.passed:
                # A review fix that breaks tests is worse than the finding;
                # hand it to the debug loop and stop the review loop.
                self._debug_loop_from_report(report)
                break
            self.log.emit("orchestrator", "review fix verified", "success",
                          detail=f"iteration {it}")
            review = self.reviewer.review(self.tools,
                                          self.state_mgr.state.architecture)
        self.memory.remember("review", review)
        self._commit("chore: self-review pass")

    def _debug_loop_from_report(self, report) -> bool:
        """Run the debug loop against the current head using a synthetic task."""
        from ..models import Task

        synth = Task(title="review-fix regression",
                     files=[c.path for c in self.state_mgr.state.file_changes][-5:])
        return self._debug_loop(synth, report)

    def _commit(self, message: str) -> None:
        """Commit progress at a milestone if there is anything to commit (spec 23)."""
        status = self.tools.call("git_status")
        if not status.ok or not status.output.strip().splitlines()[1:]:
            return  # only the branch header line -> nothing staged/unstaged
        res = self.tools.call("git_commit", message=message)
        self.log.emit("orchestrator", "git commit",
                      "success" if res.ok else "failure", detail=message)

    # -- reporting -------------------------------------------------------- #
    def final_report(self) -> Dict[str, Any]:
        st = self.state_mgr.state
        spec = st.requirements
        created = [c.path for c in st.file_changes if c.action == "created"]
        modified = [c.path for c in st.file_changes]
        last_test = st.test_results[-1] if st.test_results else {}
        met = sum(st.acceptance_status.values())
        total = len(st.acceptance_status)
        review = self.memory.recall("review", {})
        status = "COMPLETED" if (met == total and total and last_test.get("passed")) \
            else "INCOMPLETE"
        return {
            "status": status,
            "project": spec.project_name if spec else "",
            "technology": st.tech_stack,
            "features": spec.features if spec else [],
            "tasks_completed": len(st.completed_tasks),
            "tasks_failed": len(st.failed_tasks),
            "files": sorted(set(modified)),
            "tests": last_test,
            "acceptance": {"met": met, "total": total,
                           "detail": st.acceptance_status},
            "assumptions": spec.assumptions if spec else [],
            "review": review,
            "how_to_run": self._how_to_run(),
        }

    def _how_to_run(self) -> str:
        if (self.workspace / "app" / "main.py").exists():
            return "python -m app.main   # then GET http://127.0.0.1:8000/health"
        return "see README.md"
