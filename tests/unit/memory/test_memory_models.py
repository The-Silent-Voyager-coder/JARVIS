"""Memory model tests: invariants, validation, serialization, helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from jarvis.exceptions import MemoryValidationError
from jarvis.memory.models import (
    Memory,
    MemoryFilter,
    MemoryRetrieval,
    MemoryType,
    Provenance,
    RankedMemory,
    content_text,
    is_expired,
    new_memory_id,
    utcnow,
)


def _memory(**overrides) -> Memory:
    fields = {
        "id": "mem_test_1",
        "memory_type": MemoryType.LONG_TERM,
        "content": "hello world",
        "source": "user",
        "provenance": Provenance.USER_EXPLICIT.value,
        "confidence": 0.8,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    fields.update(overrides)
    return Memory(**fields)


def test_new_memory_id_format_and_uniqueness() -> None:
    first = new_memory_id()
    second = new_memory_id()
    assert first.startswith("mem_")
    assert len(first) == 4 + 32
    assert first != second


def test_utcnow_is_timezone_aware() -> None:
    assert utcnow().tzinfo is not None


def test_memory_type_values() -> None:
    assert [t.value for t in MemoryType] == [
        "working",
        "long_term",
        "episodic",
        "semantic",
    ]


def test_valid_memory_passes_validation() -> None:
    _memory().validate()


def test_structured_content_round_trip() -> None:
    memory = _memory(content={"kind": "preference", "value": "dark mode"}, metadata={"k": 1})
    memory.validate()
    assert content_text(memory.content) == '{"kind": "preference", "value": "dark mode"}'


def test_empty_content_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="content"):
        _memory(content="   ").validate()
    with pytest.raises(MemoryValidationError, match="content"):
        _memory(content={}).validate()
    with pytest.raises(MemoryValidationError, match="content"):
        _memory(content=[]).validate()


def test_non_json_content_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="JSON"):
        _memory(content=object()).validate()


def test_empty_source_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="source"):
        _memory(source=" ").validate()


def test_empty_provenance_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="provenance"):
        _memory(provenance="").validate()


def test_oversized_provenance_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="provenance"):
        _memory(provenance="x" * 101).validate()


@pytest.mark.parametrize("bad", [-0.1, 1.1, True, "0.8"])
def test_invalid_confidence_rejected(bad) -> None:
    with pytest.raises(MemoryValidationError, match="confidence"):
        _memory(confidence=bad).validate()


def test_no_confidence_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="confidence"):
        _memory(confidence=None).validate()


def test_naive_datetimes_rejected() -> None:
    naive = datetime.now()
    with pytest.raises(MemoryValidationError, match="created_at"):
        _memory(created_at=naive).validate()
    with pytest.raises(MemoryValidationError, match="expires_at"):
        _memory(expires_at=naive).validate()


def test_non_serializable_metadata_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="metadata"):
        _memory(metadata={"bad": object()}).validate()


def test_invalid_memory_type_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="memory type"):
        _memory(memory_type="ephemeral").validate()


def test_empty_id_rejected() -> None:
    with pytest.raises(MemoryValidationError, match="id"):
        _memory(id="").validate()


def test_is_expired() -> None:
    now = utcnow()
    assert not is_expired(_memory())  # no expiry
    assert not is_expired(_memory(expires_at=now + timedelta(days=1)), now=now)
    assert is_expired(_memory(expires_at=now - timedelta(seconds=1)), now=now)


def test_content_text_forms() -> None:
    assert content_text("plain") == "plain"
    assert content_text({"a": 1}) == '{"a": 1}'
    assert content_text([1, 2]) == "[1, 2]"


def test_to_dict_hides_content_unless_requested() -> None:
    memory = _memory(content="secret note")
    data = memory.to_dict(include_content=False)
    assert "content" not in data
    assert data["id"] == "mem_test_1"
    assert data["type"] == "long_term"
    assert data["confidence"] == 0.8
    assert "expires_at" in data
    full = memory.to_dict(include_content=True)
    assert full["content"] == "secret note"


def test_ranked_memory_to_dict() -> None:
    ranked = RankedMemory(memory=_memory(), score=0.9, match_reason="query match: x")
    data = ranked.to_dict(include_content=False)
    assert data["score"] == 0.9
    assert data["match_reason"] == "query match: x"
    assert "content" not in data


def test_memory_retrieval_shape() -> None:
    retrieval = MemoryRetrieval(items=[], total=0)
    assert retrieval.items == []
    assert retrieval.total == 0


def test_filter_validation() -> None:
    MemoryFilter().validate()
    MemoryFilter(minimum_confidence=0.5).validate()
    with pytest.raises(MemoryValidationError, match="minimum_confidence"):
        MemoryFilter(minimum_confidence=1.5).validate()
    with pytest.raises(MemoryValidationError, match="created_after"):
        MemoryFilter(created_after=datetime.now()).validate()
