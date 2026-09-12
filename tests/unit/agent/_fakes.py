"""Shared fakes for the agent-layer unit tests (offline, no I/O)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from greatsage.exceptions import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionDeniedError,
    ToolValidationError,
)
from greatsage.intelligence.models import (
    AIRequest,
    AIResponse,
    FinishReason,
    TokenUsage,
    ToolCall,
)
from greatsage.intelligence.provider import Capability, ProviderCapabilities, ProviderState
from greatsage.tools.approval import DeterministicApprovalProvider
from greatsage.tools.models import ApprovalOutcome, ToolRequest, ToolResult

_Handler = Callable[[AIRequest], AIResponse]


def _response(
    request: AIRequest,
    *,
    content: str,
    finish: FinishReason,
    tool_calls: list[ToolCall] | None = None,
) -> AIResponse:
    return AIResponse(
        request_id=request.request_id,
        provider="fake",
        model="fake-model",
        content=content,
        finish_reason=finish,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        tool_calls=tool_calls,
    )


def text_handler(text: str = "done", finish: FinishReason = FinishReason.STOP) -> _Handler:
    """A scripted handler that answers with plain text."""

    def handle(request: AIRequest) -> AIResponse:
        return _response(request, content=text, finish=finish)

    return handle


def tool_handler(
    tool_id: str | None = None,
    arguments: dict[str, Any] | None = None,
    count: int = 1,
    *,
    allow_empty: bool = False,
) -> _Handler:
    """A scripted handler that requests tool calls (names come from schemas)."""

    def handle(request: AIRequest) -> AIResponse:
        calls: list[ToolCall] = []
        fallback = request.tools[0].name if request.tools else "filesystem.list"
        for index in range(count):
            name = tool_id if (allow_empty or tool_id) else fallback
            calls.append(
                ToolCall(
                    id=f"call_{index + 1}",
                    name=name,
                    arguments=dict(arguments or {}),
                )
            )
        return _response(
            request, content="", finish=FinishReason.TOOL_CALL, tool_calls=calls
        )

    return handle


class FakeIntelligence:
    """Stand-in for IntelligenceService: scripted, deterministic, offline."""

    def __init__(
        self,
        handlers: list[_Handler] | None = None,
        *,
        keep_last: bool = True,
    ) -> None:
        self._queue: deque[_Handler] = deque(handlers or [])
        self._fallback: _Handler | None = None
        self._keep_last = keep_last
        self.requests: list[AIRequest] = []
        self.raise_exc: BaseException | None = None
        self.cancelled: list[str] = []

    def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self._queue:
            handler = self._queue.popleft()
            if self._keep_last or not self._queue:
                self._fallback = handler
        elif self._fallback is not None:
            handler = self._fallback
        else:
            handler = text_handler("mock:empty")
        return handler(request)

    def cancel(self, request_id: str) -> None:
        self.cancelled.append(request_id)


def gate_handler(
    entered: Any,
    release: Any,
    *,
    tool_call: bool = False,
) -> _Handler:
    """A scripted handler that blocks until the test releases the run.

    Used to pause an orchestrator run mid-flight (health/cancellation).
    """

    def handle(request: AIRequest) -> AIResponse:
        entered.set()
        release.wait(timeout=30)
        if tool_call:
            return _response(
                request,
                content="",
                finish=FinishReason.TOOL_CALL,
                tool_calls=[ToolCall(id="call_1", name="filesystem.list", arguments={})],
            )
        return _response(request, content="released", finish=FinishReason.STOP)

    return handle


class FakeProvider:
    """Minimal AIProvider surface for the agent capability/state gate."""

    def __init__(
        self,
        provider_id: str = "fake",
        *,
        tool_calling: bool = True,
        state: ProviderState = ProviderState.READY,
    ) -> None:
        self._provider_id = provider_id
        caps = {Capability.TEXT_GENERATION}
        if tool_calling:
            caps.add(Capability.TOOL_CALLING)
        self._capabilities = ProviderCapabilities(capabilities=frozenset(caps))
        self._state = state

    def provider_id(self) -> str:
        return self._provider_id

    @property
    def state(self) -> ProviderState:
        return self._state

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities


class FakeProviderRegistry:
    """ProviderRegistry surface the agent service gate depends on."""

    def __init__(self, providers: dict[str, FakeProvider] | None = None) -> None:
        self._providers = dict(providers or {})

    def has(self, provider_id: str) -> bool:
        return provider_id in self._providers

    def get(self, provider_id: str) -> FakeProvider:
        if provider_id not in self._providers:
            raise KeyError(provider_id)
        return self._providers[provider_id]

    def ids(self) -> tuple[str, ...]:
        return tuple(self._providers)


class FakeToolRegistry:
    """Stand-in for the ToolRegistry: list_ids + describe only."""

    def __init__(self, tools: dict[str, dict[str, Any]] | None = None) -> None:
        self._tools = tools or {
            "filesystem.list": {
                "description": "List directory entries",
                "input_schema": {"type": "object"},
            }
        }

    def list_ids(self) -> list[str]:
        return sorted(self._tools)

    def describe(self, tool_id: str) -> dict[str, Any]:
        if tool_id not in self._tools:
            raise ToolNotFoundError(f"tool not found: {tool_id}")
        return {
            "id": tool_id,
            "name": tool_id,
            "description": self._tools[tool_id]["description"],
            "input_schema": dict(self._tools[tool_id]["input_schema"]),
        }


class DenyApproval:
    """Approval provider that always denies."""

    def request_approval(
        self, request: ToolRequest, tool: Any, reason: str
    ) -> ApprovalOutcome:
        return ApprovalOutcome.DENIED


_UNSET = object()


class _dummy_tool:
    """Minimal stand-in for a Tool object passed to an ApprovalProvider."""

    pass


class FakeTools:
    """Stand-in for ToolService: mirrors its security pipeline surface.

    Every tool call must pass through :meth:`execute`, so agent tests prove
    there is no bypass of the tool execution path.
    """

    def __init__(
        self,
        *,
        approval: Any = _UNSET,
        registry: FakeToolRegistry | None = None,
        outputs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.approval: Any = (
            approval
            if approval is not _UNSET
            else DeterministicApprovalProvider(ApprovalOutcome.APPROVED)
        )
        self._registry = registry or FakeToolRegistry()
        self._outputs = dict(outputs or {})
        self._unknown: set[str] = set()
        self._invalid: set[str] = set()
        self._crash: set[str] = set()
        self._failures: dict[str, str] = {}
        self._requires_approval: set[str] = set()
        self.calls: list[ToolRequest] = []

    def registry(self) -> FakeToolRegistry:
        return self._registry

    def mark_unknown(self, tool_id: str) -> None:
        self._unknown.add(tool_id)

    def mark_invalid(self, tool_id: str) -> None:
        self._invalid.add(tool_id)

    def mark_crash(self, tool_id: str) -> None:
        self._crash.add(tool_id)

    def mark_failure(self, tool_id: str, error: str = "tool failed") -> None:
        self._failures[tool_id] = error

    def mark_requires_approval(self, tool_id: str) -> None:
        self._requires_approval.add(tool_id)

    def execute(self, request: ToolRequest) -> ToolResult:
        self.calls.append(request)
        if request.tool_id in self._unknown:
            raise ToolNotFoundError(f"unknown tool: {request.tool_id}")
        if request.tool_id in self._invalid:
            raise ToolValidationError(f"invalid arguments for {request.tool_id}")
        if request.tool_id in self._crash:
            raise ToolExecutionError(f"tool crashed: {request.tool_id}")
        if request.tool_id in self._requires_approval:
            if self.approval is None:
                raise ToolPermissionDeniedError(
                    "no approval provider configured; request denied"
                )
            outcome = self.approval.request_approval(request, _dummy_tool(), "ask")
            if outcome is not ApprovalOutcome.APPROVED:
                raise ToolPermissionDeniedError(f"approval {outcome.value}")
        if request.tool_id in self._failures:
            return ToolResult(
                request_id=request.request_id,
                tool_id=request.tool_id,
                success=False,
                error=self._failures[request.tool_id],
                duration_ms=1.0,
            )
        output = dict(self._outputs.get(request.tool_id, {"ok": True}))
        output.setdefault("tool_id", request.tool_id)
        return ToolResult(
            request_id=request.request_id,
            tool_id=request.tool_id,
            success=True,
            output=output,
            duration_ms=1.0,
        )
