"""Working memory (RAM, session-scoped) tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from greatsage.memory.working_memory import (
    WORKING_DEFAULT_TTL_SECONDS,
    WorkingMemory,
    WorkingMemoryStore,
)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Frozen utcnow for deterministic TTL/expiry tests."""
    import greatsage.memory.working_memory as module

    now = datetime(2026, 1, 1, 12, 0, 0)
    times = {"current": now}

    def fake_now() -> datetime:
        return times["current"]

    monkeypatch.setattr(module, "utcnow", fake_now)
    return times


def test_add_returns_id_with_default_ttl(clock) -> None:
    session = WorkingMemory("s1")
    item_id = session.add("remember this")
    assert item_id.startswith("wm_")
    item = session.get(item_id)
    assert item is not None
    assert item.session_id == "s1"
    expected = clock["current"] + timedelta(seconds=WORKING_DEFAULT_TTL_SECONDS)
    assert item.expires_at == expected
    assert not item.expired


def test_zero_ttl_means_no_expiry(clock) -> None:
    session = WorkingMemory("s2")
    item_id = session.add("forever", ttl_seconds=0)
    item = session.get(item_id)
    assert item.expires_at is None
    assert not item.expired


def test_expired_item_is_purged_on_get(clock) -> None:
    session = WorkingMemory("s3")
    item_id = session.add("short lived", ttl_seconds=1)
    clock["current"] += timedelta(seconds=2)
    assert session.get(item_id) is None
    assert session.size == 0


def test_sweep_drops_expired(clock) -> None:
    session = WorkingMemory("s4")
    session.add("a", ttl_seconds=1)
    session.add("b", ttl_seconds=1)
    clock["current"] += timedelta(seconds=2)
    assert session.sweep() == 2
    assert session.size == 0


def test_list_newest_first_and_remove(clock) -> None:
    session = WorkingMemory("s5")
    old_id = session.add("old", ttl_seconds=0)
    clock["current"] += timedelta(seconds=5)
    session.add("new", ttl_seconds=0)
    listed = session.list()
    assert [item.content for item in listed] == ["new", "old"]
    assert session.remove(old_id) is True
    assert session.remove(old_id) is False
    assert [item.content for item in session.list()] == ["new"]


def test_clear(clock) -> None:
    session = WorkingMemory("s6")
    session.add("x", ttl_seconds=0)
    session.add("y", ttl_seconds=0)
    session.clear()
    assert session.size == 0


def test_store_session_isolation(clock) -> None:
    store = WorkingMemoryStore()
    first = store.session("alpha")
    second = store.session("beta")
    first_id = first.add("alpha data", ttl_seconds=0)
    second.add("beta data", ttl_seconds=0)
    assert second.get(first_id) is None
    assert first.get(first_id) is not None
    assert store.session_ids == ("alpha", "beta")
    assert store.drop("alpha") is True
    assert store.drop("alpha") is False
    assert store.session_ids == ("beta",)


def test_store_sweep_all(clock) -> None:
    store = WorkingMemoryStore()
    store.session("alpha").add("a", ttl_seconds=1)
    store.session("beta").add("b", ttl_seconds=1)
    clock["current"] += timedelta(seconds=2)
    assert store.sweep_all() == 2
    assert store.session("alpha").size == 0
    assert store.session("beta").size == 0
