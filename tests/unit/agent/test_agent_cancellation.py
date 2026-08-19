"""Cancellation token behavior (spec §13)."""

from __future__ import annotations

import pytest

from jarvis.agent.cancellation import CancellationToken
from jarvis.exceptions import AgentCancelledError


def test_not_cancelled_by_default() -> None:
    token = CancellationToken()
    assert not token.cancelled


def test_cancel_sets_flag() -> None:
    token = CancellationToken()
    token.cancel()
    assert token.cancelled


def test_raise_if_cancelled() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(AgentCancelledError, match="cancelled"):
        token.raise_if_cancelled()


def test_raise_if_not_cancelled_is_noop() -> None:
    token = CancellationToken()
    token.raise_if_cancelled()


def test_double_cancel_is_idempotent() -> None:
    token = CancellationToken()
    token.cancel()
    token.cancel()
    assert token.cancelled
