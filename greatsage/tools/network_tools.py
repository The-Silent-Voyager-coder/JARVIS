"""Network fetch tool (roadmap Phase C).

`network.fetch` performs a bounded read-only HTTP(S) GET through the standard
library only. It never sends credentials (URLs with userinfo are refused),
never touches non-HTTP schemes, and caps response bytes. Risk is MEDIUM so
every fetch is ASK-gated in normal mode.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from greatsage.tools.models import BaseTool, ToolCategory, ToolContext, ToolResult, ToolRisk

_DEFAULT_MAX_BYTES = 32768
_ABSOLUTE_MAX_BYTES = 262144


def _failure(request_id: str, tool_id: str, error: str) -> ToolResult:
    return ToolResult(request_id=request_id, tool_id=tool_id, success=False, error=error)


class NetworkFetchTool(BaseTool):
    id = "network.fetch"
    name = "Network fetch"
    description = "Bounded read-only HTTP(S) GET; text only, no credentials, no other schemes."
    version = "1.0.0"
    risk_level = ToolRisk.MEDIUM
    category = ToolCategory.NETWORK
    capabilities = ("read",)
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_bytes": {"type": "integer"},
        },
        "required": ["url"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "status": {"type": "integer"},
            "content_type": {"type": "string"},
            "truncated": {"type": "boolean"},
            "text": {"type": "string"},
        },
        "required": ["url", "status", "truncated", "text"],
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        started = time.monotonic()
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            return _failure("", self.id, "network.fetch requires a non-empty url")
        url = url.strip()
        try:
            parsed = urllib.parse.urlsplit(url)
        except ValueError as exc:
            return _failure("", self.id, f"network.fetch refuses malformed url: {exc}")
        if parsed.scheme not in ("http", "https"):
            return _failure(
                "", self.id, f"network.fetch allows http(s) only: {parsed.scheme or '-'}"
            )
        if not parsed.hostname:
            return _failure("", self.id, "network.fetch refuses url without a host")
        if parsed.username or parsed.password or "@" in parsed.netloc:
            return _failure("", self.id, "network.fetch refuses urls with credentials")
        max_bytes = arguments.get("max_bytes", _DEFAULT_MAX_BYTES)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            return _failure("", self.id, "network.fetch max_bytes must be an integer")
        max_bytes = max(1, min(max_bytes, _ABSOLUTE_MAX_BYTES))
        timeout = max(1.0, min(context.timeout_seconds, 60.0))
        request = urllib.request.Request(
            url, headers={"User-Agent": "GreatSage-local/1.0"}, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                content_type = response.headers.get("Content-Type", "")
                raw = response.read(max_bytes + 1)
        except urllib.error.HTTPError as exc:
            return _failure(
                "", self.id, f"network.fetch http error {exc.code} for {parsed.hostname}"
            )
        except urllib.error.URLError as exc:
            return _failure(
                "", self.id, f"network.fetch failed for {parsed.hostname}: {exc.reason}"
            )
        except (TimeoutError, OSError) as exc:
            return _failure("", self.id, f"network.fetch failed for {parsed.hostname}: {exc}")
        truncated = len(raw) > max_bytes
        raw = raw[:max_bytes]
        if b"\x00" in raw:
            return _failure("", self.id, "network.fetch refuses binary content")
        text = raw.decode("utf-8", errors="replace")
        duration_ms = (time.monotonic() - started) * 1000.0
        return ToolResult(
            request_id="",
            tool_id=self.id,
            success=True,
            output={
                "url": url,
                "status": status,
                "content_type": content_type,
                "truncated": truncated,
                "text": text,
            },
            duration_ms=duration_ms,
        )
