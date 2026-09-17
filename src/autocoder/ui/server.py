"""Developer web UI (spec sections 26, 27).

A dependency-free server built on the standard library. It streams the agent's
event timeline to the browser via Server-Sent Events and renders the three-panel
developer layout (project / activity / task + terminal).
"""
from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from ..config import Config
from ..core.orchestrator import Orchestrator

_STATIC = Path(__file__).parent / "static"


class _Hub:
    """Fan-out of agent events to connected SSE clients."""

    def __init__(self):
        self.clients: list[queue.Queue] = []
        self.history: list[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.running = False
        self.report: Dict[str, Any] | None = None

    def publish(self, event: Dict[str, Any]) -> None:
        with self.lock:
            self.history.append(event)
            for q in list(self.clients):
                q.put(event)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            for e in self.history[-200:]:
                q.put(e)
            self.clients.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)


def _make_handler(config: Config, hub: _Hub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, content_type="application/json"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                html = (_STATIC / "index.html").read_text(encoding="utf-8")
                return self._send(200, html, "text/html; charset=utf-8")
            if self.path == "/api/state":
                return self._send(200, json.dumps({
                    "running": hub.running, "report": hub.report,
                    "events": hub.history[-200:],
                }))
            if self.path == "/api/events":
                return self._stream_events()
            return self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            if self.path == "/api/run":
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                req = (body.get("requirement") or "").strip()
                if not req:
                    return self._send(422, json.dumps({"error": "requirement required"}))
                if hub.running:
                    return self._send(409, json.dumps({"error": "already running"}))
                threading.Thread(target=_run_agent, args=(config, hub, req),
                                 daemon=True).start()
                return self._send(202, json.dumps({"status": "started"}))
            return self._send(404, json.dumps({"error": "not found"}))

        def _stream_events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = hub.subscribe()
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                        payload = json.dumps(event)
                        self.wfile.write(f"data: {payload}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                hub.unsubscribe(q)

    return Handler


def _run_agent(config: Config, hub: _Hub, requirement: str) -> None:
    hub.running = True
    hub.report = None
    try:
        orch = Orchestrator(config, event_subscriber=hub.publish)
        hub.report = orch.run(requirement)
        hub.publish({"agent": "orchestrator", "action": "final report ready",
                     "result": "success", "detail": hub.report["status"]})
    except Exception as e:  # surface failures to the UI
        hub.publish({"agent": "orchestrator", "action": "crashed",
                     "result": "failure", "detail": str(e)})
    finally:
        hub.running = False


def serve(config: Config, host: str = "127.0.0.1", port: int = 8080) -> None:
    hub = _Hub()
    server = ThreadingHTTPServer((host, port), _make_handler(config, hub))
    print(f"autocoder UI on http://{host}:{port}  (workspace: {config.workspace})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
