"""Application inspection tools: logs, ports, health checks (spec section 10)."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request

from ..models import ToolResult


class InspectionTools:
    def check_port(self, host: str = "127.0.0.1", port: int = 8000,
                   timeout: float = 1.0) -> ToolResult:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            open_ = s.connect_ex((host, port)) == 0
        return ToolResult(ok=True, output="open" if open_ else "closed",
                          data={"open": open_, "port": port})

    def health_check(self, url: str, timeout: float = 3.0) -> ToolResult:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                body = resp.read(4096).decode("utf-8", "replace")
                return ToolResult(ok=200 <= resp.status < 300,
                                  output=f"{resp.status} {body}",
                                  data={"status": resp.status})
        except urllib.error.HTTPError as e:
            return ToolResult(ok=False, error=f"HTTP {e.code}",
                              data={"status": e.code})
        except (urllib.error.URLError, OSError) as e:
            return ToolResult(ok=False, error=str(e))

    def read_logs(self, text: str, tail: int = 100) -> ToolResult:
        lines = (text or "").splitlines()[-tail:]
        return ToolResult(ok=True, output="\n".join(lines))
