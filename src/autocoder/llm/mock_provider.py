"""Deterministic, offline LLM provider (spec sections 13, 29, 31).

This provider makes the entire autonomous loop runnable and testable without any
network access or API key. It does not "cheat" the loop: it returns *structured*
responses to the same tagged prompts the agents send to any provider, and it
deliberately ships ONE real bug on the first coding pass so the
OBSERVE -> DEBUG -> RE-TEST cycle is genuinely exercised end to end.

Agents tag each request with ``[[KIND:<name>]]`` and (where relevant)
``[[TASK:<id>]]`` so a provider can route deterministically. Live providers
ignore the tags and simply answer the natural-language prompt.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .base import LLMProvider

# --------------------------------------------------------------------------- #
# A complete, runnable target application (zero third-party dependencies) that
# the mock provider "writes" so the loop produces real, testable software.
# --------------------------------------------------------------------------- #

_STORE_BUGGY = '''"""In-memory Task store with JSON persistence."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional


class TaskStore:
    def __init__(self, path: Optional[str] = None):
        self._lock = threading.Lock()
        self._path = Path(path) if path else None
        self._items: Dict[int, dict] = {}
        self._next_id = 1
        if self._path and self._path.exists():
            self._load()

    def _load(self) -> None:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._items = {int(k): v for k, v in data.get("items", {}).items()}
        self._next_id = data.get("next_id", 1)

    def _save(self) -> None:
        if not self._path:
            return
        self._path.write_text(
            json.dumps({"items": self._items, "next_id": self._next_id}),
            encoding="utf-8",
        )

    def create(self, title: str, done: bool = False) -> dict:
        with self._lock:
            item = {"id": self._next_id, "title": title, "done": bool(done)}
            self._items[self._next_id] = item
            self._next_id += 1
            self._save()
            return dict(item)

    def list(self) -> List[dict]:
        with self._lock:
            return [dict(v) for v in self._items.values()]

    def get(self, item_id: int) -> Optional[dict]:
        with self._lock:
            item = self._items.get(item_id)
            return dict(item) if item else None

    def update(self, item_id: int, **fields) -> Optional[dict]:
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                return None
            if "title" in fields and fields["title"] is not None:
                item["title"] = fields["title"]
            if "done" in fields and fields["done"] is not None:
                item["done"] = bool(fields["done"])
            self._save()
            # BUG: returns the stale pre-update snapshot captured too early.
            return None

    def delete(self, item_id: int) -> bool:
        with self._lock:
            if item_id in self._items:
                del self._items[item_id]
                self._save()
                return True
            return False
'''

_STORE_FIXED = _STORE_BUGGY.replace(
    "            self._save()\n"
    "            # BUG: returns the stale pre-update snapshot captured too early.\n"
    "            return None\n",
    "            self._save()\n"
    "            return dict(item)\n",
)

_SERVER = '''"""A tiny REST API for Tasks built on the standard library only."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .store import TaskStore

API_TOKEN = "dev-token"  # overridden via configure(); never a real secret


def make_handler(store: TaskStore, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence default stderr logging
            pass

        def _send(self, code: int, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authed(self) -> bool:
            return self.headers.get("Authorization") == f"Bearer {token}"

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError:
                return {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self._send(200, {"status": "ok"})
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            if path == "/todos":
                return self._send(200, {"items": store.list()})
            m = _id_match(path)
            if m:
                item = store.get(m)
                if item is None:
                    return self._send(404, {"error": "not found"})
                return self._send(200, item)
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            if urlparse(self.path).path != "/todos":
                return self._send(404, {"error": "not found"})
            data = self._body()
            title = (data.get("title") or "").strip()
            if not title:
                return self._send(422, {"error": "title is required"})
            return self._send(201, store.create(title, bool(data.get("done"))))

        def do_PUT(self):
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            m = _id_match(urlparse(self.path).path)
            if not m:
                return self._send(404, {"error": "not found"})
            updated = store.update(m, **self._body())
            if updated is None:
                return self._send(404, {"error": "not found"})
            return self._send(200, updated)

        def do_DELETE(self):
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            m = _id_match(urlparse(self.path).path)
            if not m:
                return self._send(404, {"error": "not found"})
            if store.delete(m):
                return self._send(204, {})
            return self._send(404, {"error": "not found"})

    return Handler


def _id_match(path: str):
    import re

    m = re.fullmatch(r"/todos/(\\d+)", path)
    return int(m.group(1)) if m else None


def build_server(host: str = "127.0.0.1", port: int = 8000,
                 db_path=None, token: str = API_TOKEN) -> ThreadingHTTPServer:
    store = TaskStore(db_path)
    return ThreadingHTTPServer((host, port), make_handler(store, token))
'''

_MAIN = '''"""Application entrypoint: `python -m app.main`."""
from __future__ import annotations

import os

from .server import build_server


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    token = os.environ.get("API_TOKEN", "dev-token")
    server = build_server(host, port, os.environ.get("DB_PATH"), token)
    print(f"serving on http://{host}:{port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
'''

_TEST_STORE = '''"""Unit tests for the TaskStore."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.store import TaskStore


def test_create_and_get():
    s = TaskStore()
    created = s.create("write tests")
    assert created["id"] == 1
    assert created["title"] == "write tests"
    assert created["done"] is False
    assert s.get(1) == created


def test_update_returns_fresh_item():
    s = TaskStore()
    s.create("draft")
    updated = s.update(1, title="final", done=True)
    assert updated is not None, "update must return the updated item"
    assert updated["title"] == "final"
    assert updated["done"] is True


def test_delete():
    s = TaskStore()
    s.create("temp")
    assert s.delete(1) is True
    assert s.get(1) is None
    assert s.delete(1) is False


def test_persistence(tmp_path):
    db = tmp_path / "db.json"
    s1 = TaskStore(str(db))
    s1.create("persist me")
    s2 = TaskStore(str(db))
    assert s2.get(1)["title"] == "persist me"
'''

_TEST_API = '''"""Integration test: spin up the real HTTP server and exercise CRUD."""
import json
import os
import sys
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.server import build_server

TOKEN = "dev-token"


def _req(method, url, body=None, token=TOKEN):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, json.loads(raw) if raw else {}


def test_full_crud_workflow():
    server = build_server(port=0, token=TOKEN)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        status, _ = _req("GET", base + "/health", token=None)
        assert status == 200

        # Unauthorized access is rejected.
        status, _ = _req("GET", base + "/todos", token=None)
        assert status == 401

        status, created = _req("POST", base + "/todos", {"title": "buy milk"})
        assert status == 201 and created["id"] == 1

        status, listing = _req("GET", base + "/todos")
        assert status == 200 and len(listing["items"]) == 1

        status, updated = _req("PUT", base + f"/todos/1", {"done": True})
        assert status == 200 and updated["done"] is True

        status, _ = _req("DELETE", base + "/todos/1")
        assert status == 204

        status, _ = _req("GET", base + "/todos/1")
        assert status == 404
    finally:
        server.shutdown()
'''

_README = '''# Task API

A small REST API for managing tasks, built with the Python standard library
(no third-party dependencies). Generated and verified by the autocoder agent.

## Run

```bash
python -m app.main         # serves on http://127.0.0.1:8000
```

## Endpoints

| Method | Path          | Auth | Description        |
|--------|---------------|------|--------------------|
| GET    | /health       | no   | Liveness probe     |
| GET    | /todos        | yes  | List tasks         |
| POST   | /todos        | yes  | Create a task      |
| GET    | /todos/{id}   | yes  | Fetch one task     |
| PUT    | /todos/{id}   | yes  | Update a task      |
| DELETE | /todos/{id}   | yes  | Delete a task      |

Auth is a bearer token (`Authorization: Bearer dev-token`).

## Test

```bash
python -m pytest tests/
```
'''

_BLUEPRINT: Dict[str, str] = {
    "app/__init__.py": '"""Task API application package."""\n',
    "app/store.py": _STORE_FIXED,  # replaced per-attempt in the provider
    "app/server.py": _SERVER,
    "app/main.py": _MAIN,
    "tests/test_store.py": _TEST_STORE,
    "tests/test_api.py": _TEST_API,
    "README.md": _README,
}


class MockProvider(LLMProvider):
    """Routes tagged requests to deterministic structured responses."""

    name = "mock"

    def __init__(self, inject_bug: bool = True):
        self.inject_bug = inject_bug
        self._debug_done = False  # flips once a debug fix is requested

    # -- public API ------------------------------------------------------- #
    def generate(self, prompt: str, *, system=None, model=None,
                 temperature=0.2, max_tokens=4096) -> str:
        return json.dumps(self._route(prompt))

    def generate_structured(self, prompt: str, *, system=None, model=None,
                            schema_hint=None, temperature=0.1,
                            max_tokens=4096) -> Dict[str, Any]:
        return self._route(prompt)

    # -- routing ---------------------------------------------------------- #
    def _kind(self, prompt: str) -> str:
        m = re.search(r"\[\[KIND:([a-z_]+)\]\]", prompt)
        return m.group(1) if m else "unknown"

    def _task_id(self, prompt: str) -> str:
        m = re.search(r"\[\[TASK:([^\]]+)\]\]", prompt)
        return m.group(1) if m else ""

    def _route(self, prompt: str) -> Dict[str, Any]:
        kind = self._kind(prompt)
        handler = getattr(self, f"_k_{kind}", None)
        if handler is None:
            return {"note": "no handler", "kind": kind}
        return handler(prompt)

    # -- handlers --------------------------------------------------------- #
    def _k_requirement_analysis(self, prompt: str) -> Dict[str, Any]:
        return {
            "project_name": "task-api",
            "description": "A REST API to manage tasks with token authentication.",
            "objectives": [
                "Expose CRUD endpoints for tasks",
                "Protect write operations with authentication",
                "Persist data reliably",
            ],
            "functional_requirements": [
                "Create, read, update, delete tasks",
                "List all tasks",
                "Health-check endpoint",
                "Bearer-token authentication on protected routes",
            ],
            "non_functional_requirements": [
                "No external runtime dependencies",
                "Automated tests for store and API",
            ],
            "users": ["API client", "developer"],
            "roles": ["authenticated user"],
            "features": ["task CRUD", "auth", "persistence", "health check"],
            "integrations": [],
            "constraints": ["standard library only"],
            "technology_preferences": ["Python"],
            "acceptance_criteria": [
                "Application starts successfully",
                "Unauthorized users cannot access protected endpoints",
                "A task can be created",
                "A task can be updated",
                "A task can be deleted",
                "Unit tests pass",
                "Integration tests pass",
            ],
            "implied_requirements": [
                "Input validation on create",
                "404 handling for missing tasks",
            ],
            "assumptions": [
                "A single shared bearer token is acceptable for this scope",
                "In-process JSON persistence is sufficient (no external DB)",
            ],
        }

    def _k_tech_selection(self, prompt: str) -> Dict[str, Any]:
        return {
            "language": "Python",
            "backend": "http.server (stdlib)",
            "frontend": "none",
            "database": "JSON file (stdlib)",
            "testing_framework": "pytest",
            "package_manager": "pip",
            "reasoning": (
                "The requirement is a self-contained REST API. The standard "
                "library covers HTTP serving, JSON, and persistence, which "
                "maximizes maintainability and deployment simplicity with zero "
                "dependency risk. pytest is used for tests as it is ubiquitous."
            ),
        }

    def _k_architecture(self, prompt: str) -> Dict[str, Any]:
        return {
            "layers": ["HTTP handler", "business logic", "data store"],
            "folders": ["app/", "tests/"],
            "entities": [
                {"name": "Task", "fields": ["id:int", "title:str", "done:bool"]}
            ],
            "endpoints": [
                {"method": "GET", "path": "/health", "auth": False},
                {"method": "GET", "path": "/todos", "auth": True},
                {"method": "POST", "path": "/todos", "auth": True},
                {"method": "GET", "path": "/todos/{id}", "auth": True},
                {"method": "PUT", "path": "/todos/{id}", "auth": True},
                {"method": "DELETE", "path": "/todos/{id}", "auth": True},
            ],
        }

    def _k_planning(self, prompt: str) -> Dict[str, Any]:
        return {
            "tasks": [
                {
                    "title": "Create application package",
                    "phase": "Foundation",
                    "description": "Initialize the app package.",
                    "files": ["app/__init__.py"],
                    "acceptance_criteria": ["package imports"],
                },
                {
                    "title": "Implement task store",
                    "phase": "Core Features",
                    "description": "In-memory store with JSON persistence and CRUD.",
                    "files": ["app/store.py"],
                    "acceptance_criteria": [
                        "create/get/update/delete work",
                        "persistence round-trips",
                    ],
                },
                {
                    "title": "Implement REST server",
                    "phase": "Core Features",
                    "description": "HTTP handler exposing CRUD with auth.",
                    "files": ["app/server.py", "app/main.py"],
                    "acceptance_criteria": [
                        "endpoints respond",
                        "auth enforced",
                    ],
                },
                {
                    "title": "Write automated tests",
                    "phase": "Testing",
                    "description": "Unit and integration tests.",
                    "files": ["tests/test_store.py", "tests/test_api.py"],
                    "acceptance_criteria": ["tests execute"],
                },
                {
                    "title": "Write documentation",
                    "phase": "Validation",
                    "description": "README with run/test instructions.",
                    "files": ["README.md"],
                    "acceptance_criteria": ["README present"],
                },
            ]
        }

    def _k_coding(self, prompt: str) -> Dict[str, Any]:
        """Return file contents for the files named in the current task."""
        files: List[Dict[str, str]] = []
        wanted = re.findall(r"\[\[FILE:([^\]]+)\]\]", prompt)
        for path in wanted:
            content = _BLUEPRINT.get(path)
            if content is None:
                continue
            if path == "app/store.py" and self.inject_bug and not self._debug_done:
                content = _STORE_BUGGY
            files.append({"path": path, "action": "write", "content": content})
        return {
            "reason": "Implementing the files required by the current task.",
            "files": files,
            "commands": [],
            "tests": [],
            "confidence": 0.9,
        }

    def _k_debug(self, prompt: str) -> Dict[str, Any]:
        """Diagnose the failing store test and emit the corrected file."""
        self._debug_done = True
        return {
            "category": "TestFailure",
            "root_cause": (
                "TaskStore.update returned None instead of the updated item, so "
                "callers could not observe the change."
            ),
            "files": [
                {"path": "app/store.py", "action": "write", "content": _STORE_FIXED}
            ],
            "commands": [],
            "confidence": 0.95,
        }

    def _k_test_analysis(self, prompt: str) -> Dict[str, Any]:
        passed = "FAILED" not in prompt and "Error" not in prompt
        return {
            "passed": passed,
            "failures": [] if passed else ["see raw output"],
            "recommendations": [] if passed else ["fix TaskStore.update return value"],
        }

    def _k_review(self, prompt: str) -> Dict[str, Any]:
        return {
            "issues": [],
            "security": [],
            "summary": (
                "Architecture is coherent and minimal. Auth is enforced on write "
                "routes. No hardcoded production secrets; the dev token is "
                "clearly marked and overridable via environment."
            ),
            "approved": True,
        }
