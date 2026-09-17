from autocoder.core.memory import MemoryManager
from autocoder.core.state import StateManager
from autocoder.models import ErrorRecord, Task, TaskStatus


def test_state_persist_and_reload(tmp_path):
    sm = StateManager(tmp_path)
    t = Task(title="one")
    sm.state.task_queue = [t]
    sm.state.user_requirement = "build x"
    sm.save()

    sm2 = StateManager(tmp_path)
    assert sm2.load()
    assert sm2.state.user_requirement == "build x"
    assert sm2.state.task_queue[0].title == "one"


def test_dependency_ordering(tmp_path):
    sm = StateManager(tmp_path)
    a = Task(title="a")
    b = Task(title="b", dependencies=[a.id])
    sm.state.task_queue = [a, b]
    # b is blocked until a completes.
    assert sm.next_pending_task().id == a.id
    sm.record_task_result(a, True)
    assert sm.next_pending_task().id == b.id


def test_memory_detects_repeated_failure(tmp_path):
    mem = MemoryManager(tmp_path)
    rec = ErrorRecord(error="AssertionError: boom", category="TestFailure",
                      file="app/x.py", solution="tried A")
    mem.record_error(rec)
    same = ErrorRecord(error="AssertionError: boom", category="TestFailure",
                       file="app/x.py")
    assert mem.seen_before(same) is not None
    assert "tried A" in mem.prior_solutions(same)


def test_memory_project_recall(tmp_path):
    mem = MemoryManager(tmp_path)
    mem.remember("stack", {"lang": "python"})
    mem2 = MemoryManager(tmp_path)
    assert mem2.recall("stack")["lang"] == "python"
