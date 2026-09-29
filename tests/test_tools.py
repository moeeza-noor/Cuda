from autocoder.config import Config
from autocoder.tools.registry import ToolRegistry


def _reg(tmp_path):
    return ToolRegistry(Config(workspace=tmp_path, require_confirmation=True))


def test_write_read_edit(tmp_path):
    reg = _reg(tmp_path)
    assert reg.call("write_file", path="a/b.py", content="x=1\n").ok
    assert reg.call("read_file", path="a/b.py").output == "x=1\n"
    assert reg.call("edit_file", path="a/b.py", old="x=1", new="x=2").ok
    assert reg.call("read_file", path="a/b.py").output == "x=2\n"


def test_edit_requires_unique(tmp_path):
    reg = _reg(tmp_path)
    reg.call("write_file", path="d.py", content="a\na\n")
    assert not reg.call("edit_file", path="d.py", old="a", new="b").ok


def test_search_code(tmp_path):
    reg = _reg(tmp_path)
    reg.call("write_file", path="m.py", content="def hello():\n    pass\n")
    res = reg.call("search_code", pattern="def hello", glob="*.py")
    assert res.data["count"] == 1


def test_sandbox_blocks_escape(tmp_path):
    reg = _reg(tmp_path)
    assert not reg.call("write_file", path="../evil.txt", content="x").ok


def test_blocked_command_not_run(tmp_path):
    reg = _reg(tmp_path)
    res = reg.call("run_command", command="rm -rf /")
    assert not res.ok and "BLOCKED" in res.error


def test_confirmation_denied_by_default(tmp_path):
    reg = _reg(tmp_path)
    res = reg.call("run_command", command="pip install requests")
    assert not res.ok and "confirmation" in res.error


def test_safe_command_runs(tmp_path):
    reg = _reg(tmp_path)
    res = reg.call("run_command", command="echo hello")
    assert res.ok and "hello" in res.output


def test_unknown_tool(tmp_path):
    reg = _reg(tmp_path)
    assert not reg.call("nope").ok
