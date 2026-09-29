"""Browser / UI automation tools (spec section 21).

Optional: requires the `browser` extra (`pip install autocoder[browser]`). The
core loop never depends on this — the import is guarded so a bare install runs
fine, and the tool simply reports unavailability if Playwright is missing.

Used to verify *actual user workflows* (open → click → type → submit → inspect)
rather than only checking that files compile.
"""
from __future__ import annotations

import os
from typing import List, Optional

from ..models import ToolResult

# Common locations for the preinstalled Chromium in managed environments.
_CHROMIUM_CANDIDATES = [
    os.path.join(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""), "chromium"),
    "/opt/pw-browsers/chromium",
]


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401

        return True
    except Exception:
        return False


class BrowserTools:
    """A thin, session-scoped wrapper over Playwright's sync API."""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._page = None
        self._console_errors: List[str] = []

    # -- lifecycle -------------------------------------------------------- #
    def _ensure(self) -> Optional[ToolResult]:
        if self._page is not None:
            return None
        if not playwright_available():
            return ToolResult(
                ok=False,
                error="Playwright not installed. `pip install autocoder[browser]`",
            )
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        launch_kwargs = {"headless": True}
        for cand in _CHROMIUM_CANDIDATES:
            if cand and os.path.exists(cand):
                launch_kwargs["executable_path"] = cand
                break
        try:
            self._browser = self._pw.chromium.launch(**launch_kwargs)
        except Exception:
            # Fall back to Playwright's own resolution if executable_path failed.
            self._browser = self._pw.chromium.launch(headless=True)
        self._page = self._browser.new_page()
        self._page.on("console", self._on_console)
        self._page.on("pageerror",
                      lambda exc: self._console_errors.append(str(exc)))
        return None

    def _on_console(self, msg) -> None:
        if msg.type in ("error", "warning"):
            self._console_errors.append(f"{msg.type}: {msg.text}")

    def close(self) -> ToolResult:
        for obj, meth in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj is not None:
                    getattr(obj, meth)()
            except Exception:
                pass
        self._pw = self._browser = self._page = None
        self._console_errors = []
        return ToolResult(ok=True, output="browser closed")

    # -- actions ---------------------------------------------------------- #
    def navigate(self, url: str, timeout_ms: int = 10000) -> ToolResult:
        err = self._ensure()
        if err:
            return err
        try:
            resp = self._page.goto(url, timeout=timeout_ms)
            status = resp.status if resp else 0
            return ToolResult(ok=status == 0 or 200 <= status < 400,
                              output=f"navigated to {url} ({status})",
                              data={"status": status})
        except Exception as e:
            return ToolResult(ok=False, error=f"navigate failed: {e}")

    def click(self, selector: str, timeout_ms: int = 5000) -> ToolResult:
        err = self._ensure()
        if err:
            return err
        try:
            self._page.click(selector, timeout=timeout_ms)
            return ToolResult(ok=True, output=f"clicked {selector}")
        except Exception as e:
            return ToolResult(ok=False, error=f"click failed: {e}")

    def type_text(self, selector: str, text: str,
                  timeout_ms: int = 5000) -> ToolResult:
        err = self._ensure()
        if err:
            return err
        try:
            self._page.fill(selector, text, timeout=timeout_ms)
            return ToolResult(ok=True, output=f"typed into {selector}")
        except Exception as e:
            return ToolResult(ok=False, error=f"type failed: {e}")

    def text_content(self, selector: str = "body",
                     timeout_ms: int = 5000) -> ToolResult:
        err = self._ensure()
        if err:
            return err
        try:
            txt = self._page.text_content(selector, timeout=timeout_ms) or ""
            return ToolResult(ok=True, output=txt.strip()[:4000],
                              data={"text": txt})
        except Exception as e:
            return ToolResult(ok=False, error=f"read failed: {e}")

    def screenshot(self, path: str) -> ToolResult:
        err = self._ensure()
        if err:
            return err
        try:
            self._page.screenshot(path=path)
            return ToolResult(ok=True, output=f"screenshot saved to {path}",
                              data={"path": path})
        except Exception as e:
            return ToolResult(ok=False, error=f"screenshot failed: {e}")

    def console_errors(self) -> ToolResult:
        return ToolResult(ok=True, output="\n".join(self._console_errors),
                          data={"errors": list(self._console_errors)})
