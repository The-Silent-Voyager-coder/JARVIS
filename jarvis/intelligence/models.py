"""Provider-neutral intelligence models: messages, requests, responses, streaming.

Everything the core and the router see is defined here; provider adapters
translate their vendor-specific wire formats to and from these types. No
provider-specific structures leak into the core (docs/ARCHITECTURE.md §4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from jarvis.exceptions import ValidationError


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    CONTENT_FILTERED = "content_filtered"
    CANCELLED = "cancelled"
    ERROR = "error"


class TaskKind(StrEnum):
    """Routing hint: what kind of task the request serves."""

    GENERAL = "general"
    CODING = "coding"


# --- structured content parts --------------------------------------------


@dataclass(frozen=True)
class TextPart:
    kind: Literal["text"] = "text"
    text: str = ""


@dataclass(frozen=True)
class ToolCallPart:
    kind: Literal["tool_call"] = "tool_call"
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


ContentPart = TextPart | ToolCallPart


@dataclass(frozen=True)
class Message:
    """A single conversation message with a typed role."""

    role: Role
    content: str | list[ContentPart] = ""
    tool_call_id: str | None = None
    name: str | None = None

    @classmethod
    def system(cls, text: str) -> Message:
        return cls(role=Role.SYSTEM, content=text)

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(role=Role.USER, content=text)

    @classmethod
    def assistant(cls, text: str) -> Message:
        return cls(role=Role.ASSISTANT, content=text)

    @classmethod
    def tool(cls, tool_call_id: str, text: str) -> Message:
        return cls(role=Role.TOOL, content=text, tool_call_id=tool_call_id)


@dataclass(frozen=True)
class ToolDefinition:
    """A tool the model may call (provider-neutral subset)."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenUsage:
    """Token accounting; a provider that does not report a field leaves it None.

    Never fabricate token counts (docs/ARCHITECTURE.md verification rules).
    """

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @property
    def available(self) -> bool:
        return self.total_tokens is not None or (
            self.prompt_tokens is not None and self.completion_tokens is not None
        )


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AIRequest:
    """Provider-neutral generation request.

    Not every provider supports every field; support is declared through
    ProviderCapabilities. Requested-but-unsupported behavior is an explicit
    error at the provider boundary, never a silent ignore.
    """

    messages: list[Message]
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[ToolDefinition] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout: float | None = None

    def validate(self) -> None:
        """Validate the request contract; raise ValidationError on violations."""
        if not self.messages:
            raise ValidationError("AIRequest requires at least one message")
        for message in self.messages:
            if not isinstance(message, Message):
                raise ValidationError("messages must contain Message instances")
            if message.role is Role.TOOL and not message.tool_call_id:
                raise ValidationError("tool messages require tool_call_id")
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValidationError(f"temperature must be in 0.0..2.0, got {self.temperature}")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValidationError(f"max_tokens must be >= 1, got {self.max_tokens}")
        if self.timeout is not None and self.timeout <= 0:
            raise ValidationError(f"timeout must be positive, got {self.timeout}")


@dataclass(frozen=True)
class AIResponse:
    """Provider-neutral completion response."""

    request_id: str
    provider: str
    model: str
    content: str | None = None
    finish_reason: FinishReason = FinishReason.STOP
    usage: TokenUsage | None = None
    tool_calls: list[ToolCall] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StreamChunk:
    """Provider-neutral streaming chunk.

    Kinds: text (delta), tool_call (delta), metadata (side information),
    completion (final summary), error (terminal failure).
    """

    kind: Literal["text", "tool_call", "metadata", "completion", "error"]
    text: str = ""
    tool_call_id: str | None = None
    name: str | None = None
    arguments: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    finish_reason: FinishReason | None = None
    usage: TokenUsage | None = None

    @classmethod
    def text_delta(cls, delta: str) -> StreamChunk:
        return cls(kind="text", text=delta)

    @classmethod
    def tool_call_delta(
        cls, tool_call_id: str | None, name: str | None, arguments: str
    ) -> StreamChunk:
        return cls(
            kind="tool_call", tool_call_id=tool_call_id, name=name, arguments=arguments
        )

    @classmethod
    def completion(
        cls,
        finish_reason: FinishReason,
        usage: TokenUsage | None = None,
    ) -> StreamChunk:
        return cls(kind="completion", finish_reason=finish_reason, usage=usage)

    @classmethod
    def error_chunk(cls, message: str) -> StreamChunk:
        return cls(kind="error", error=message)


# --- simplest display helper ---------------------------------------------


def message_text(message: Message) -> str:
    """Plain-text rendering of a message's content (for logs/CLI only)."""
    if isinstance(message.content, str):
        return message.content
    parts: list[str] = []
    for part in message.content:
        if isinstance(part, TextPart):
            parts.append(part.text)
        else:
            parts.append(f"[tool_call:{part.name}]")
    return "".join(parts)


def format_response(response: AIResponse) -> str:
    """Human-readable render of a complete response (CLI/observability)."""
    if response.tool_calls:
        calls = ", ".join(f"{c.name}({c.id})" for c in response.tool_calls)
        return f"tool_calls={calls}"
    return response.content or ""


def now_utc() -> datetime:
    return datetime.now(UTC)
