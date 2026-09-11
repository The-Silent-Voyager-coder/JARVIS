"""Home Assistant tools (roadmap Phase C).

`homeassistant.states` (LOW) reads entity states; `homeassistant.call`
(HIGH, always ASK-gated) invokes a service (lights, switches, scripts…).
Both speak to Home Assistant's HTTP API through the standard library only.

Configuration is environment-only (secrets policy — never files):
`HA_BASE_URL` (e.g. http://homeassistant.local:8123) and `HA_TOKEN`
(a long-lived access token). Without both, every call fails closed with a
"not configured" error. The token is used in the Authorization header only
and never logged, persisted, or returned in output.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from jarvis.tools.models import BaseTool, ToolCategory, ToolContext, ToolResult, ToolRisk

_BASE_URL_ENV = "HA_BASE_URL"
_TOKEN_ENV = "HA_TOKEN"
_ENTITY_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_SERVICE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _config() -> tuple[str, str] | None:
    base = (os.environ.get(_BASE_URL_ENV) or "").strip().rstrip("/")
    token = os.environ.get(_TOKEN_ENV) or ""
    if not base or not token:
        return None
    try:
        parsed = urllib.parse.urlsplit(base)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return base, token


def _failure(tool_id: str, error: str) -> ToolResult:
    return ToolResult(request_id="", tool_id=tool_id, success=False, error=error)


def _api(
    tool_id: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> ToolResult:
    configured = _config()
    if configured is None:
        return _failure(
            tool_id,
            "homeassistant not configured (set HA_BASE_URL + HA_TOKEN environment variables)",
        )
    base, token = configured
    started = time.monotonic()
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "JARVIS-local/1.0",
    }
    if payload is not None:
        try:
            data = json.dumps(payload).encode("utf-8")
        except (TypeError, ValueError):
            return _failure(tool_id, "homeassistant payload is not JSON-serializable")
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(65537)
    except urllib.error.HTTPError as exc:
        return _failure(tool_id, f"homeassistant http error {exc.code}")
    except urllib.error.URLError as exc:
        return _failure(tool_id, f"homeassistant unreachable: {exc.reason}")
    except (TimeoutError, OSError) as exc:
        return _failure(tool_id, f"homeassistant request failed: {exc}")
    truncated = len(raw) > 65536
    try:
        body: Any = json.loads(raw[:65536].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _failure(tool_id, "homeassistant returned non-JSON content")
    return ToolResult(
        request_id="",
        tool_id=tool_id,
        success=True,
        output={"truncated": truncated, "result": body},
        duration_ms=(time.monotonic() - started) * 1000.0,
    )


class HomeAssistantStatesTool(BaseTool):
    id = "homeassistant.states"
    name = "Home Assistant states"
    description = "Read entity states from Home Assistant (read-only)."
    version = "1.0.0"
    risk_level = ToolRisk.LOW
    category = ToolCategory.NETWORK
    capabilities = ("read",)
    input_schema = {
        "type": "object",
        "properties": {"entity_id": {"type": "string"}},
        "required": [],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "truncated": {"type": "boolean"},
            "result": {"type": "object"},
        },
        "required": ["result"],
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        entity_id = arguments.get("entity_id")
        path = "/api/states"
        if entity_id is not None:
            if not isinstance(entity_id, str) or not _ENTITY_RE.match(entity_id.strip()):
                return _failure(self.id, "homeassistant entity_id must look like domain.name")
            path += "/" + entity_id.strip()
        timeout = max(1.0, min(context.timeout_seconds, 30.0))
        return _api(self.id, "GET", path, None, timeout)


class HomeAssistantCallTool(BaseTool):
    id = "homeassistant.call"
    name = "Home Assistant service call"
    description = "Invoke a Home Assistant service (acts on the home; always ASK-gated)."
    version = "1.0.0"
    risk_level = ToolRisk.HIGH
    category = ToolCategory.NETWORK
    capabilities = ("act",)
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "service": {"type": "string"},
            "entity_id": {"type": "string"},
            "data": {"type": "object"},
        },
        "required": ["domain", "service"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "truncated": {"type": "boolean"},
            "result": {"type": "object"},
        },
        "required": ["result"],
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        domain = arguments.get("domain")
        service = arguments.get("service")
        if not isinstance(domain, str) or not _SERVICE_RE.match(domain.strip()):
            return _failure(self.id, "homeassistant domain must be a plain service domain")
        if not isinstance(service, str) or not _SERVICE_RE.match(service.strip()):
            return _failure(self.id, "homeassistant service must be a plain service name")
        payload: dict[str, Any] = {}
        entity_id = arguments.get("entity_id")
        if entity_id is not None:
            if not isinstance(entity_id, str) or not _ENTITY_RE.match(entity_id.strip()):
                return _failure(self.id, "homeassistant entity_id must look like domain.name")
            payload["entity_id"] = entity_id.strip()
        data = arguments.get("data")
        if data is not None:
            if not isinstance(data, dict):
                return _failure(self.id, "homeassistant data must be an object")
            payload.update(data)
        path = f"/api/services/{domain.strip()}/{service.strip()}"
        timeout = max(1.0, min(context.timeout_seconds, 30.0))
        return _api(self.id, "POST", path, payload, timeout)
