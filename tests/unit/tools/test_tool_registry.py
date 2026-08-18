"""ToolRegistry tests (spec §6, §24, §25, §39)."""

from __future__ import annotations

import pytest

from jarvis.exceptions import ToolNotFoundError, ToolValidationError
from jarvis.tools.models import ToolCategory, ToolRisk
from jarvis.tools.registry import ToolRegistry
from tests.unit.tools.stub_tools import StubProbe


class FakeTool:
    """Duck-typed object with an id but not a Tool contract."""

    id = "fake.tool"


def make_probe(risk: ToolRisk = ToolRisk.SAFE, name: str = "probe.info") -> StubProbe:
    return StubProbe(
        name=name,
        description=f"test probe {name}",
        category=ToolCategory.SYSTEM,
        risk=risk,
    )


def test_register_and_lookup() -> None:
    reg = ToolRegistry()
    tool = make_probe()
    reg.register(tool)
    assert reg.get("probe.info") is tool
    assert reg.list_ids() == ("probe.info",)
    assert list(reg.enumerate()) == [tool]


def test_get_unknown_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError, match="unknown tool"):
        reg.get("missing")


def test_duplicate_register_rejected() -> None:
    reg = ToolRegistry()
    reg.register(make_probe())
    with pytest.raises(ToolValidationError, match="duplicate tool id"):
        reg.register(make_probe())


def test_register_non_tool_rejected() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolValidationError, match="does not implement"):
        reg.register(FakeTool())  # type: ignore[arg-type]


def test_register_invalid_schema_rejected() -> None:
    reg = ToolRegistry()
    tool = make_probe()
    tool.input_schema = {"type": "array"}  # type: ignore[assignment]
    with pytest.raises(ToolValidationError):
        reg.register(tool)


def test_unregister() -> None:
    reg = ToolRegistry()
    reg.register(make_probe())
    assert reg.unregister("probe.info") is True
    assert reg.unregister("probe.info") is False
    assert reg.list_ids() == ()


def test_describe_contains_schemas_no_arguments() -> None:
    reg = ToolRegistry()
    reg.register(make_probe())
    desc = reg.describe("probe.info")
    assert desc["id"] == "probe.info"
    assert desc["risk_level"] == "safe"
    assert desc["category"] == "system"
    assert desc["input_schema"]["properties"]["value"]["type"] == "integer"
    assert "arguments" not in desc


def test_describe_unknown_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        reg.describe("missing")


def test_health_reports_count_and_ids() -> None:
    reg = ToolRegistry()
    reg.register(make_probe(name="probe.a"))
    reg.register(make_probe(name="probe.b"))
    health = reg.health()
    assert health["status"] == "healthy"
    assert health["tool_count"] == 2
    assert health["tools"] == ("probe.a", "probe.b")
