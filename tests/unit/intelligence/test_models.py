"""Intelligence model tests: request validation, roles, structured content,
response shape, usage fidelity, stream chunk kinds."""

from __future__ import annotations

import pytest

from jarvis.exceptions import ValidationError
from jarvis.intelligence.models import (
    AIRequest,
    AIResponse,
    FinishReason,
    Message,
    Role,
    StreamChunk,
    TextPart,
    TokenUsage,
    ToolCallPart,
    ToolDefinition,
)


def test_request_defaults_and_ids() -> None:
    request = AIRequest(messages=[Message.user("hello")])
    assert request.request_id
    assert len(request.request_id) >= 8
    assert request.system_prompt is None
    assert request.temperature is None
    assert request.max_tokens is None
    assert request.tools is None
    assert request.metadata == {}


def test_request_validation_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        AIRequest(messages=[]).validate()


def test_request_validation_rejects_non_message() -> None:
    with pytest.raises(ValidationError):
        AIRequest(messages=[{"role": "user", "content": "x"}]).validate()


def test_request_validation_tool_message_requires_tool_call_id() -> None:
    with pytest.raises(ValidationError):
        AIRequest(messages=[Message.tool(None, "result")]).validate()


def test_request_validation_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        AIRequest(messages=[Message.user("hi")], temperature=3.0).validate()


def test_request_validation_max_tokens() -> None:
    with pytest.raises(ValidationError):
        AIRequest(messages=[Message.user("hi")], max_tokens=0).validate()


def test_request_validation_timeout() -> None:
    with pytest.raises(ValidationError):
        AIRequest(messages=[Message.user("hi")], timeout=-1.0).validate()


def test_roles_enum() -> None:
    assert Role.SYSTEM.value == "system"
    assert Role.USER.value == "user"
    assert Role.ASSISTANT.value == "assistant"
    assert Role.TOOL.value == "tool"


def test_message_constructors() -> None:
    system = Message.system("be concise")
    user = Message.user("summarize")
    assistant = Message.assistant("done")
    tool = Message.tool("call_1", "result")
    assert system.role is Role.SYSTEM
    assert user.role is Role.USER
    assert assistant.role is Role.ASSISTANT
    assert tool.role is Role.TOOL
    assert tool.tool_call_id == "call_1"


def test_structured_content_parts() -> None:
    message = Message(
        role=Role.ASSISTANT,
        content=[
            TextPart(text="thoughts"),
            ToolCallPart(id="c1", name="search", arguments={"q": "x"}),
        ],
    )
    parts = message.content
    assert isinstance(parts, list)
    assert parts[0].kind == "text"
    assert parts[1].kind == "tool_call"
    assert parts[1].name == "search"


def test_tool_definition() -> None:
    tool = ToolDefinition(
        name="search",
        description="search the web",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    assert tool.input_schema["type"] == "object"


def test_usage_availability() -> None:
    assert TokenUsage().available is False
    assert TokenUsage(total_tokens=10).available is True
    assert TokenUsage(prompt_tokens=5, completion_tokens=5).available is True
    assert TokenUsage(prompt_tokens=5, completion_tokens=None).available is False


def test_response_fields() -> None:
    response = AIResponse(
        request_id="r1",
        provider="mock",
        model="mock-model",
        content="answer",
        finish_reason=FinishReason.STOP,
        usage=TokenUsage(total_tokens=12),
    )
    assert response.content == "answer"
    assert response.finish_reason is FinishReason.STOP
    assert response.usage is not None
    assert response.usage.total_tokens == 12
    assert response.tool_calls is None


def test_stream_chunk_constructors() -> None:
    text = StreamChunk.text_delta("hi")
    assert text.kind == "text"
    assert text.text == "hi"
    done = StreamChunk.completion(FinishReason.STOP)
    assert done.kind == "completion"
    err = StreamChunk.error_chunk("boom")
    assert err.kind == "error"
    assert err.error == "boom"
    call = StreamChunk.tool_call_delta("c1", "search", "{}")
    assert call.kind == "tool_call"
    assert call.name == "search"


def test_finish_reasons() -> None:
    assert FinishReason.CANCELLED.value == "cancelled"
    assert FinishReason.TOOL_CALL.value == "tool_call"
    assert FinishReason.CONTENT_FILTERED.value == "content_filtered"
