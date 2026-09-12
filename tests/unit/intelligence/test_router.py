"""Router tests — the ten documented deterministic routing scenarios.

1. explicit provider selection wins (metadata hint)
2. explicit selection of an unavailable provider -> error, never fallback
3. explicit selection of an unknown provider -> error
4. no hint -> configured default provider used
5. capability filter: require_streaming drops non-streaming providers
6. tools declared -> providers without TOOL_CALLING are filtered out
7. CODING task_kind -> prefers the remote code-execution provider
8. no coding -> local-only provider preferred
9. no candidate -> RoutingError with alternatives
10. model filter: request.model not in provider model_ids -> provider skipped
"""

from __future__ import annotations

import pytest

from greatsage.exceptions import RoutingError
from greatsage.intelligence.mock import MockProvider
from greatsage.intelligence.models import AIRequest, Message, TaskKind
from greatsage.intelligence.provider import Capability
from greatsage.intelligence.registry import ProviderRegistry
from greatsage.intelligence.router import Router


@pytest.fixture
def registry() -> ProviderRegistry:
    return ProviderRegistry()


def _router(registry: ProviderRegistry, default: str | None = None) -> Router:
    return Router(registry, default_provider=default)


def _ready(provider: MockProvider) -> MockProvider:
    provider.init()
    return provider


def _request(**kwargs) -> AIRequest:
    metadata = kwargs.pop("metadata", {})
    return AIRequest(messages=[Message.user("hello")], metadata=metadata, **kwargs)


# 1. explicit provider selection wins -------------------------------


def test_explicit_provider_via_metadata(registry: ProviderRegistry) -> None:
    local = _ready(MockProvider("local"))
    opencode = _ready(MockProvider("opencode"))
    registry.register(local)
    registry.register(opencode)
    route = _router(registry).route(_request(metadata={"provider": "opencode"}))
    assert route.selected_provider == "opencode"
    assert route.requested_provider == "opencode"
    assert "explicit selection" in route.reason


# 2. explicit selection never falls back ----------------------------


def test_explicit_unavailable_provider_errors(registry: ProviderRegistry) -> None:
    broken = _ready(MockProvider("broken"))
    broken.shutdown()  # STOPPED providers are never routed to
    ready = _ready(MockProvider("ready"))
    registry.register(broken)
    registry.register(ready)
    with pytest.raises(RoutingError, match="does not fall back"):
        _router(registry).route(_request(metadata={"provider": "broken"}))


# 3. unknown explicit provider --------------------------------------


def test_explicit_unknown_provider_errors(registry: ProviderRegistry) -> None:
    registry.register(_ready(MockProvider("local")))
    with pytest.raises(RoutingError, match="not registered"):
        _router(registry).route(_request(metadata={"provider": "ghost"}))


# 4. default provider -----------------------------------------------


def test_default_provider_used_without_hint(registry: ProviderRegistry) -> None:
    registry.register(_ready(MockProvider("a")))
    registry.register(_ready(MockProvider("b")))
    route = _router(registry, default="b").route(_request())
    assert route.selected_provider == "b"
    assert route.requested_provider == "b"


# 5. streaming capability filter ------------------------------------


def test_streaming_required_filters_non_streaming(registry: ProviderRegistry) -> None:
    plain = _ready(MockProvider("plain"))
    streamer = _ready(MockProvider("streamer", capabilities={Capability.STREAMING}))
    registry.register(plain)
    registry.register(streamer)
    route = _router(registry).route(_request(metadata={"require_streaming": True}))
    assert route.selected_provider == "streamer"


# 6. tool calling capability filter ---------------------------------


def test_tools_require_tool_calling_provider(registry: ProviderRegistry) -> None:
    from greatsage.intelligence.models import ToolDefinition

    plain = _ready(MockProvider("plain"))
    tooling = _ready(MockProvider("tooling", capabilities={Capability.TOOL_CALLING}))
    registry.register(plain)
    registry.register(tooling)
    request = _request(
        tools=[ToolDefinition(name="f", description="d")],
    )
    route = _router(registry).route(request)
    assert route.selected_provider == "tooling"


# 7. coding task prefers remote code execution ----------------------


def test_coding_task_prefers_code_execution(registry: ProviderRegistry) -> None:
    local = _ready(MockProvider("local", capabilities={Capability.LOCAL}))
    opencode = _ready(
        MockProvider(
            "opencode",
            capabilities={Capability.REMOTE, Capability.CODE_EXECUTION},
        )
    )
    registry.register(local)
    registry.register(opencode)
    route = _router(registry).route(
        _request(metadata={"task_kind": TaskKind.CODING.value})
    )
    assert route.selected_provider == "opencode"
    assert "code execution" in route.reason


# 8. local preferred otherwise --------------------------------------


def test_local_preferred_for_general_tasks(registry: ProviderRegistry) -> None:
    remote = _ready(MockProvider("remote", capabilities={Capability.REMOTE}))
    local = _ready(MockProvider("local", capabilities={Capability.LOCAL}))
    registry.register(remote)
    registry.register(local)
    route = _router(registry).route(_request())
    assert route.selected_provider == "local"
    assert "local provider preferred" in route.reason


# 9. no candidate -> error with alternatives ------------------------


def test_no_capable_provider_errors_with_alternatives(registry: ProviderRegistry) -> None:
    plain = _ready(MockProvider("plain"))
    registry.register(plain)
    with pytest.raises(RoutingError, match="no provider available"):
        _router(registry).route(_request(metadata={"require_streaming": True}))


def test_no_providers_at_all(registry: ProviderRegistry) -> None:
    with pytest.raises(RoutingError, match="none registered"):
        _router(registry).route(_request())


# 10. model filter --------------------------------------------------


def test_model_mismatch_skips_provider(registry: ProviderRegistry) -> None:
    llama = _ready(MockProvider("llama", model_ids=("llama3",)))
    gpt = _ready(MockProvider("gpt", model_ids=("gpt-4",)))
    registry.register(llama)
    registry.register(gpt)
    route = _router(registry).route(_request(model="gpt-4"))
    assert route.selected_provider == "gpt"


# observability: route carries alternatives -------------------------


def test_route_records_alternatives(registry: ProviderRegistry) -> None:
    a = _ready(MockProvider("a"))
    b = _ready(MockProvider("b"))
    registry.register(a)
    registry.register(b)
    route = _router(registry, default="a").route(_request())
    assert set(route.alternatives) == {"a", "b"}
    payload = route.to_dict()
    assert payload["requested_provider"] == "a"
    assert payload["selected_provider"] == "a"
