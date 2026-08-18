"""Mock provider tests: deterministic generation, streaming, failure modes,
cancellation, capability gating."""

from __future__ import annotations

import asyncio

import pytest

from jarvis.exceptions import ProviderCapabilityError, ProviderError
from jarvis.intelligence.mock import MockProvider
from jarvis.intelligence.models import AIRequest, Message, ToolDefinition
from jarvis.intelligence.provider import Capability, ProviderState


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider()


def test_generate_deterministic(provider: MockProvider) -> None:
    request = AIRequest(messages=[Message.user("hello world")])
    first = provider.generate(request)
    second = provider.generate(AIRequest(messages=[Message.user("hello world")]))
    assert first.provider == "mock"
    assert first.content == "mock:hello world"
    assert first.request_id == request.request_id
    assert second.content == first.content


def test_mock_starts_ready(provider: MockProvider) -> None:
    assert provider.state is ProviderState.READY
    assert provider.health().ok


def test_init_keeps_ready(provider: MockProvider) -> None:
    provider.init()
    assert provider.state is ProviderState.READY
    assert provider.health().ok


def test_generate_usage(provider: MockProvider) -> None:
    provider.init()
    response = provider.generate(AIRequest(messages=[Message.user("abc")]))
    assert response.usage is not None
    assert response.usage.prompt_tokens == 3
    assert response.usage.total_tokens == 7


def test_failure_mode(provider: MockProvider) -> None:
    provider.fail_on_generate = True
    provider.init()
    assert provider.health().ok is False
    with pytest.raises(ProviderError, match="configured to fail"):
        provider.generate(AIRequest(messages=[Message.user("x")]))


def test_force_error_metadata(provider: MockProvider) -> None:
    provider.init()
    request = AIRequest(messages=[Message.user("x")], metadata={"force_error": True})
    with pytest.raises(ProviderError, match="forced error"):
        provider.generate(request)


def test_streaming_default_unsupported(provider: MockProvider) -> None:
    with pytest.raises(ProviderCapabilityError, match="streaming"):
        run(_collect(provider))


def test_streaming_with_capability() -> None:
    provider = MockProvider(capabilities={Capability.STREAMING})
    provider.init()
    chunks = run(_collect(provider))
    text = "".join(chunk.text for chunk in chunks if chunk.kind == "text")
    assert text
    assert any(chunk.kind == "completion" for chunk in chunks)


async def _collect(provider: MockProvider):
    request = AIRequest(messages=[Message.user("stream me please")])
    return [chunk async for chunk in provider.stream(request)]


def test_stream_error_chunk() -> None:
    provider = MockProvider(capabilities={Capability.STREAMING})
    provider.init()
    request = AIRequest(messages=[Message.user("x")], metadata={"force_error": True})
    chunks = run(_collect_request(provider, request))
    assert chunks[-1].kind == "error"


async def _collect_request(provider: MockProvider, request: AIRequest):
    return [chunk async for chunk in provider.stream(request)]


def test_cancel_requires_capability(provider: MockProvider) -> None:
    provider.init()
    with pytest.raises(ProviderCapabilityError, match="cancellation"):
        provider.cancel("req-1")


def test_cancel_supported() -> None:
    provider = MockProvider(capabilities={Capability.STREAMING, Capability.CANCELLATION})
    provider.init()
    provider.cancel("req-1")
    assert "req-1" in provider._cancelled


def test_tool_calling_gate() -> None:
    provider = MockProvider()
    provider.init()
    request = AIRequest(
        messages=[Message.user("x")],
        tools=[ToolDefinition(name="f", description="d")],
    )
    with pytest.raises(ProviderCapabilityError, match="tool_calling"):
        provider.generate(request)


def test_tool_calling_supported() -> None:
    from jarvis.intelligence.models import ToolDefinition

    provider = MockProvider(capabilities={Capability.TOOL_CALLING})
    provider.init()
    request = AIRequest(
        messages=[Message.user("query data")],
        tools=[ToolDefinition(name="lookup", description="lookup")],
    )
    response = provider.generate(request)
    assert response.tool_calls is not None
    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].arguments == {"query": "query data"}
