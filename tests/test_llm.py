from autocoder.llm.base import extract_json
from autocoder.llm.mock_provider import MockProvider


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert extract_json('here:\n```json\n{"a": 2}\n```\nthanks')["a"] == 2


def test_extract_json_embedded():
    assert extract_json('noise {"a": {"b": 3}} trailing')["a"]["b"] == 3


def test_mock_routes_by_kind():
    p = MockProvider()
    spec = p.generate_structured("[[KIND:requirement_analysis]] build a task api")
    assert spec["project_name"] == "task-api"
    plan = p.generate_structured("[[KIND:planning]] plan it")
    assert len(plan["tasks"]) == 5


def test_mock_injects_then_fixes_bug():
    p = MockProvider(inject_bug=True)
    first = p.generate_structured("[[KIND:coding]] [[FILE:app/store.py]]")
    assert "return None" in first["files"][0]["content"]
    p.generate_structured("[[KIND:debug]] fix it")
    after = p.generate_structured("[[KIND:coding]] [[FILE:app/store.py]]")
    assert "return dict(item)" in after["files"][0]["content"]
