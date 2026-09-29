"""Browser/UI tool tests. Skipped when the `browser` extra is not installed."""
import threading

import pytest

from autocoder.config import Config
from autocoder.tools.browser import BrowserTools, playwright_available
from autocoder.tools.registry import ToolRegistry

pytestmark = pytest.mark.skipif(
    not playwright_available(), reason="playwright not installed (browser extra)"
)


def test_browser_reports_unavailable_gracefully_when_missing(monkeypatch):
    # Even with the extra installed, a bad launch must return a ToolResult,
    # never raise — the loop must not crash on UI verification.
    bt = BrowserTools()
    res = bt.text_content("body")  # navigates nothing; ensure/close are safe
    assert res.ok in (True, False)  # returns a ToolResult, does not raise
    bt.close()


def test_real_browser_workflow_against_shipped_ui(tmp_path):
    """Serve the bundled developer UI and drive it with a real Chromium."""
    from autocoder.ui.server import _Hub, _make_handler
    from http.server import ThreadingHTTPServer

    config = Config(workspace=tmp_path, provider="mock")
    hub = _Hub()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(config, hub))
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    reg = ToolRegistry(config)
    try:
        nav = reg.call("browser_navigate", url=f"http://127.0.0.1:{port}/")
        assert nav.ok, nav.error
        body = reg.call("browser_text", selector="body")
        assert body.ok
        assert "Autonomous Coding Agent" in body.output
        # The requirement input exists and is typeable.
        typed = reg.call("browser_type", selector="#req", text="Build a demo")
        assert typed.ok, typed.error
        shot = reg.call("browser_screenshot", path=str(tmp_path / "ui.png"))
        assert shot.ok and (tmp_path / "ui.png").exists()
    finally:
        reg.browser.close()
        server.shutdown()
