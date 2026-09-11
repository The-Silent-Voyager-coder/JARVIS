"""Network + Home Assistant tool tests (roadmap Phase C, offline)."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from jarvis.tools.homeassistant_tools import HomeAssistantCallTool, HomeAssistantStatesTool
from jarvis.tools.models import ToolCategory, ToolContext, ToolRisk
from jarvis.tools.network_tools import NetworkFetchTool


def _context() -> ToolContext:
    return ToolContext(
        working_directory=Path("."),
        environment={},
        timeout_seconds=5.0,
        max_output_bytes=65536,
    )


class _FakeHeaders:
    def __init__(self, content_type: str = "text/html") -> None:
        self._content_type = content_type

    def get(self, name: str, default: str = "") -> str:
        return self._content_type if name.lower() == "content-type" else default


class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status
        self.headers = _FakeHeaders()

    def read(self, n: int = -1) -> bytes:
        return self._body if n is None or n < 0 else self._body[:n]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_tool_declarations() -> None:
    fetch = NetworkFetchTool()
    assert fetch.category is ToolCategory.NETWORK
    assert fetch.risk_level is ToolRisk.MEDIUM
    states = HomeAssistantStatesTool()
    assert states.risk_level is ToolRisk.LOW
    call = HomeAssistantCallTool()
    assert call.risk_level is ToolRisk.HIGH


def test_fetch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(b"hello world")
    )
    result = NetworkFetchTool().execute({"url": "https://example.com/"}, _context())
    assert result.success is True
    assert result.output is not None
    assert result.output["text"] == "hello world"
    assert result.output["status"] == 200
    assert result.output["truncated"] is False


def test_fetch_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _FakeResponse(b"x" * 100)
    )
    result = NetworkFetchTool().execute(
        {"url": "https://example.com/", "max_bytes": 10}, _context()
    )
    assert result.success is True
    assert result.output is not None
    assert result.output["truncated"] is True
    assert len(result.output["text"]) == 10


def test_fetch_rejects_bad_urls() -> None:
    tool = NetworkFetchTool()
    assert tool.execute({"url": "ftp://example.com/x"}, _context()).success is False
    assert tool.execute({"url": "file:///etc/passwd"}, _context()).success is False
    assert tool.execute({"url": "https://user:pass@example.com/"}, _context()).success is False
    assert tool.execute({"url": "https://"}, _context()).success is False
    assert tool.execute({"url": ""}, _context()).success is False
    bad_size = {"url": "https://example.com", "max_bytes": "lots"}
    assert tool.execute(bad_size, _context()).success is False


def test_fetch_refuses_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _FakeResponse(b"\x89PNG\x00binary"),
    )
    result = NetworkFetchTool().execute({"url": "https://example.com/a.png"}, _context())
    assert result.success is False


def test_fetch_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(req: object, timeout: object = None) -> _FakeResponse:
        raise urllib.error.HTTPError(str(req), 404, "nope", {}, io.BytesIO())

    monkeypatch.setattr("urllib.request.urlopen", boom)
    result = NetworkFetchTool().execute({"url": "https://example.com/missing"}, _context())
    assert result.success is False
    assert "404" in (result.error or "")


def test_ha_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HA_BASE_URL", raising=False)
    monkeypatch.delenv("HA_TOKEN", raising=False)
    result = HomeAssistantStatesTool().execute({}, _context())
    assert result.success is False
    assert "not configured" in (result.error or "")
    result = HomeAssistantCallTool().execute(
        {"domain": "light", "service": "turn_on"}, _context()
    )
    assert result.success is False


def test_ha_states(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HA_BASE_URL", "http://ha.local:8123")
    monkeypatch.setenv("HA_TOKEN", "token-abc")
    seen: dict[str, Any] = {}

    def fake(req: object, timeout: object = None) -> _FakeResponse:
        seen["url"] = req.full_url  # type: ignore[union-attr]
        seen["auth"] = req.headers.get("Authorization")  # type: ignore[union-attr]
        body = json.dumps([{"entity_id": "light.lamp", "state": "on"}]).encode()
        return _FakeResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", fake)
    result = HomeAssistantStatesTool().execute({}, _context())
    assert result.success is True
    assert seen["url"] == "http://ha.local:8123/api/states"
    assert seen["auth"] == "Bearer token-abc"

    result = HomeAssistantStatesTool().execute({"entity_id": "light.lamp"}, _context())
    assert result.success is True
    assert seen["url"].endswith("/api/states/light.lamp")
    assert HomeAssistantStatesTool().execute({"entity_id": "../evil"}, _context()).success is False


def test_ha_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HA_BASE_URL", "http://ha.local:8123")
    monkeypatch.setenv("HA_TOKEN", "token-abc")
    seen: dict[str, Any] = {}

    def fake(req: object, timeout: object = None) -> _FakeResponse:
        seen["url"] = req.full_url  # type: ignore[union-attr]
        seen["data"] = json.loads(req.data.decode())  # type: ignore[union-attr]
        return _FakeResponse(b"[]")

    monkeypatch.setattr("urllib.request.urlopen", fake)
    result = HomeAssistantCallTool().execute(
        {"domain": "light", "service": "turn_on",
         "entity_id": "light.lamp", "data": {"brightness": 100}},
        _context(),
    )
    assert result.success is True
    assert seen["url"] == "http://ha.local:8123/api/services/light/turn_on"
    assert seen["data"] == {"entity_id": "light.lamp", "brightness": 100}
    assert "token-abc" not in json.dumps(result.output)

    tool = HomeAssistantCallTool()
    assert tool.execute({"domain": "light/../x", "service": "turn_on"}, _context()).success is False
    assert tool.execute({"domain": "light"}, _context()).success is False
