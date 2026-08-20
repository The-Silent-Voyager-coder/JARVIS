"""OpenCode adapter tests against an in-process fake HTTP server.

Covers /global/health, /doc spec fetch, session creation, prompt, response
handling, malformed/timeout/server-error paths, abort, capabilities, and the
delegation surface (sessions, SSE events, permissions). No real OpenCode
server, no internet.
"""

from __future__ import annotations

import asyncio

import pytest

from jarvis.delegation.models import DelegationEventKind
from jarvis.exceptions import ProviderCapabilityError, ProviderError, ProviderUnavailableError
from jarvis.intelligence.models import AIRequest, Message, ToolDefinition
from jarvis.intelligence.opencode import OpenCodeProvider
from jarvis.intelligence.provider import Capability, ProviderState

OPENCODE_HEALTH = {"ok": True, "service": "opencode", "version": "0.1.0"}
OPENCODE_SPEC = {"openapi": "3.1.0", "info": {"title": "opencode server"}}
SESSION_ID = "sess-123"
PROMPT_RESPONSE = {
    "id": "resp-1",
    "content": "code answer",
    "model": "opencode-model",
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def opencode(fake_server) -> OpenCodeProvider:
    fake_server.route("GET", "/global/health", 200, OPENCODE_HEALTH)
    fake_server.route("GET", "/doc", 200, OPENCODE_SPEC)
    provider = OpenCodeProvider(base_url=fake_server.url)
    return provider


def test_health_and_capabilities(opencode: OpenCodeProvider, fake_server) -> None:
    health = opencode.health()
    assert health.ok
    assert health.state is ProviderState.READY
    caps = opencode.capabilities()
    assert caps.supports(Capability.REMOTE)
    assert caps.supports(Capability.CODE_EXECUTION)
    assert caps.supports(Capability.CANCELLATION)
    assert not caps.supports(Capability.STREAMING)


def test_health_unavailable(fake_server) -> None:
    provider = OpenCodeProvider(base_url="http://127.0.0.1:1", timeout_seconds=1.0)
    health = provider.health()
    assert health.ok is False
    assert health.state is ProviderState.UNAVAILABLE


def test_health_malformed(fake_server) -> None:
    fake_server.route("GET", "/global/health", 200, "not-json")
    provider = OpenCodeProvider(base_url=fake_server.url)
    health = provider.health()
    assert health.ok is False
    assert health.state is ProviderState.DEGRADED


def test_health_negative_ok_field(fake_server) -> None:
    fake_server.route("GET", "/global/health", 200, {"ok": False, "reason": "busy"})
    provider = OpenCodeProvider(base_url=fake_server.url)
    health = provider.health()
    assert health.ok is False
    assert health.state is ProviderState.DEGRADED


def test_generate_sessions_and_prompt(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 200, {"id": SESSION_ID})
    fake_server.route(
        "POST", f"/session/{SESSION_ID}/prompt", 200, PROMPT_RESPONSE
    )
    fake_server.route("DELETE", f"/session/{SESSION_ID}", 200, {"ok": True})
    opencode.init()
    response = opencode.generate(AIRequest(messages=[Message.user("write code")]))
    assert response.provider == "opencode"
    assert response.content == "code answer"
    assert response.model == "opencode-model"
    assert response.finish_reason.value == "stop"
    assert response.usage is not None
    assert response.usage.total_tokens == 14
    methods = [req["method"] for req in fake_server.requests]
    assert "POST" in methods
    assert "DELETE" in methods
    prompt_request = next(
        r for r in fake_server.requests if "prompt" in r["path"]
    )
    assert '"role": "user"' in prompt_request["body"]
    assert "prompt_async" in prompt_request["body"]


def test_generate_system_prompt(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 200, {"id": SESSION_ID})
    fake_server.route(
        "POST", f"/session/{SESSION_ID}/prompt", 200, PROMPT_RESPONSE
    )
    fake_server.route("DELETE", f"/session/{SESSION_ID}", 200, {"ok": True})
    opencode.init()
    opencode.generate(
        AIRequest(
            messages=[Message.user("hi")],
            system_prompt="you are a code assistant",
            model="claude-sonnet",
        )
    )
    prompt_request = next(r for r in fake_server.requests if "prompt" in r["path"])
    assert '"system"' in prompt_request["body"]
    assert '"model": "claude-sonnet"' in prompt_request["body"]


def test_generate_usage_absent_is_none(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 200, {"id": SESSION_ID})
    fake_server.route(
        "POST",
        f"/session/{SESSION_ID}/prompt",
        200,
        {"content": "no usage here", "finish_reason": "stop"},
    )
    fake_server.route("DELETE", f"/session/{SESSION_ID}", 200, {"ok": True})
    opencode.init()
    response = opencode.generate(AIRequest(messages=[Message.user("hi")]))
    assert response.usage is None
    assert response.content == "no usage here"


def test_generate_session_creation_failure(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 500, {"error": "boom"})
    opencode.init()
    with pytest.raises(ProviderError, match="session"):
        opencode.generate(AIRequest(messages=[Message.user("hi")]))


def test_generate_missing_session_id(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 200, {})
    opencode.init()
    with pytest.raises(ProviderError, match="session id"):
        opencode.generate(AIRequest(messages=[Message.user("hi")]))


def test_generate_unreachable(fake_server) -> None:
    provider = OpenCodeProvider(base_url="http://127.0.0.1:1", timeout_seconds=1.0)
    provider.init()
    with pytest.raises(ProviderUnavailableError):
        provider.generate(AIRequest(messages=[Message.user("hi")]))


def test_generate_server_error(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 200, {"id": SESSION_ID})
    fake_server.route("POST", f"/session/{SESSION_ID}/prompt", 500, {"error": "x"})
    fake_server.route("DELETE", f"/session/{SESSION_ID}", 200, {"ok": True})
    opencode.init()
    with pytest.raises(ProviderError, match="HTTP 500"):
        opencode.generate(AIRequest(messages=[Message.user("hi")]))


def test_tools_unsupported_explicit_error(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 200, {"id": SESSION_ID})
    fake_server.route("POST", f"/session/{SESSION_ID}/prompt", 200, PROMPT_RESPONSE)
    fake_server.route("DELETE", f"/session/{SESSION_ID}", 200, {"ok": True})
    opencode.init()
    request = AIRequest(
        messages=[Message.user("hi")],
        tools=[ToolDefinition(name="f", description="d")],
    )
    with pytest.raises(ProviderCapabilityError, match="tool_calling"):
        opencode.generate(request)


def test_stream_not_supported_explicit_error(opencode: OpenCodeProvider) -> None:
    opencode.init()

    async def collect():
        request = AIRequest(messages=[Message.user("hi")])
        return [chunk async for chunk in opencode.stream(request)]

    with pytest.raises(ProviderCapabilityError, match="streaming"):
        run(collect())


def test_cancel_noop(opencode: OpenCodeProvider) -> None:
    opencode.init()
    opencode.cancel("req-1")  # must not raise


def test_api_key_env_used(fake_server, monkeypatch) -> None:
    fake_server.route("GET", "/global/health", 200, OPENCODE_HEALTH)
    monkeypatch.setenv("JARVIS_OPENCODE_TOKEN", "sk-test")
    provider = OpenCodeProvider(
        base_url=fake_server.url, api_key_env="JARVIS_OPENCODE_TOKEN"
    )
    provider.init()
    provider._auth_headers()  # force load
    assert provider._api_key == "sk-test"


def test_timeout_hits(fake_server) -> None:
    fake_server.route("GET", "/global/health", 200, OPENCODE_HEALTH)
    fake_server.slow("/global/health")
    provider = OpenCodeProvider(base_url=fake_server.url, timeout_seconds=0.5)
    health = provider.health()
    assert health.ok is False
    assert health.state is ProviderState.UNAVAILABLE


# --- delegation surface -----------------------------------------------


def test_capabilities_include_delegation(opencode: OpenCodeProvider) -> None:
    caps = opencode.capabilities()
    assert caps.supports(Capability.DELEGATION)


def test_create_session(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session", 200, {"id": "sess-delegated"})
    session_id = opencode.create_session()
    assert session_id == "sess-delegated"


def test_send_delegation_prompt_ok(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session/sess-1/prompt", 200, {"ok": True})
    opencode.init()
    opencode.send_delegation_prompt("sess-1", "do the work", "/tmp/project")
    prompt_request = next(r for r in fake_server.requests if "prompt" in r["path"])
    assert '"prompt_async": true' in prompt_request["body"]
    assert '"content": "do the work"' in prompt_request["body"]
    assert '"working_directory": "/tmp/project"' in prompt_request["body"]


def test_send_delegation_prompt_omits_cwd_when_absent(
    opencode: OpenCodeProvider, fake_server
) -> None:
    fake_server.route("POST", "/session/sess-1/prompt", 200, {"ok": True})
    opencode.init()
    opencode.send_delegation_prompt("sess-1", "hello")
    prompt_request = next(r for r in fake_server.requests if "prompt" in r["path"])
    assert "working_directory" not in prompt_request["body"]


def test_send_delegation_prompt_failure(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session/sess-1/prompt", 500, {"error": "boom"})
    opencode.init()
    with pytest.raises(ProviderError, match="prompt"):
        opencode.send_delegation_prompt("sess-1", "do it")


SSE_EVENTS = "\n".join(
    [
        'event: session.run.started',
        'data: {"text": "first thought"}',
        "",
        'event: session.request.permission',
        'data: {"permissionID": "perm-7", "key": {"permissions": {"action": '
        '"write", "path": "/tmp/a.txt"}}, "description": "allow write"}',
        "",
        'event: session.run.completed',
        'data: {"status": "completed", "summary": "all done"}',
        "",
    ]
)


def test_iter_session_events_translates_kinds(opencode, fake_server) -> None:
    fake_server.route("GET", "/session/sess-7/event", 200, SSE_EVENTS)
    events = list(opencode.iter_session_events("sess-7"))
    assert [e.kind for e in events] == [
        DelegationEventKind.PROGRESS,
        DelegationEventKind.PERMISSION_REQUESTED,
        DelegationEventKind.COMPLETED,
    ]
    progress = events[0]
    assert progress.message == "first thought"
    permission = events[1]
    assert permission.metadata["permission_id"] == "perm-7"
    assert permission.metadata["action"] == "write"
    assert permission.metadata["path"] == "/tmp/a.txt"
    assert permission.message == "allow write"
    completed = events[2]
    assert completed.message == "all done"


def test_iter_session_events_error_and_cancel(opencode, fake_server) -> None:
    raw = "\n".join(
        [
            'event: session.error',
            'data: {"error": "invalid token"}',
            "",
            'event: session.cancelled',
            'data: {"cancelled": true}',
            "",
        ]
    )
    fake_server.route("GET", "/session/sess-8/event", 200, raw)
    events = list(opencode.iter_session_events("sess-8"))
    assert [e.kind for e in events] == [
        DelegationEventKind.FAILED,
        DelegationEventKind.CANCELLED,
    ]
    assert events[0].message == "invalid token"


def test_iter_session_events_malformed_skipped(opencode, fake_server) -> None:
    raw = "\n".join(
        [
            'event: session.thing',
            'data: not-json',
            "",
            'event: session.thing',
            'data: [1, 2, 3]',
            "",
        ]
    )
    fake_server.route("GET", "/session/sess-9/event", 200, raw)
    events = list(opencode.iter_session_events("sess-9"))
    assert len(events) == 1
    assert events[0].kind is DelegationEventKind.NOTE


def test_iter_session_events_non_dict_data_is_note(opencode, fake_server) -> None:
    raw = "\n".join(
        [
            'event: session.thing',
            'data: "just a string"',
            "",
        ]
    )
    fake_server.route("GET", "/session/sess-10/event", 200, raw)
    events = list(opencode.iter_session_events("sess-10"))
    assert len(events) == 1
    assert events[0].kind is DelegationEventKind.NOTE


def test_respond_permission(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session/sess-1/permissions/perm-7", 200, {"ok": True})
    fake_server.route("POST", "/session/sess-1/permissions/perm-8", 200, {"ok": True})
    opencode.init()
    opencode.respond_permission("sess-1", "perm-7", True)
    opencode.respond_permission("sess-1", "perm-8", False, remember=True)
    bodies = [r["body"] for r in fake_server.requests if "permissions" in r["path"]]
    assert '"response": true' in bodies[0]
    assert '"response": false' in bodies[1]
    assert '"remember": true' in bodies[1]


def test_abort_session_never_raises(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("POST", "/session/sess-1/abort", 200, {"ok": True})
    fake_server.route("POST", "/session/missing/abort", 404, {"error": "nope"})
    opencode.init()
    opencode.abort_session("sess-1")
    opencode.abort_session("missing")  # must not raise


def test_get_session_diff(opencode: OpenCodeProvider, fake_server) -> None:
    diff = {"files": [{"path": "/tmp/a.txt", "added": 1}]}
    fake_server.route("GET", "/session/sess-1/diff", 200, diff)
    assert opencode.get_session_diff("sess-1") == diff


def test_get_session_diff_unavailable_is_none(opencode, fake_server) -> None:
    fake_server.route("GET", "/session/sess-1/diff", 500, {"error": "x"})
    assert opencode.get_session_diff("sess-1") is None


def test_dispose_session_deletes(opencode: OpenCodeProvider, fake_server) -> None:
    fake_server.route("DELETE", "/session/sess-1", 200, {"ok": True})
    opencode.init()
    opencode.dispose_session("sess-1")
    methods = [r["method"] for r in fake_server.requests]
    assert "DELETE" in methods
