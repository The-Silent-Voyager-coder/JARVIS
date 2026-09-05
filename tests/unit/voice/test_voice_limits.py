"""Voice limit tests: defaults, ceilings, smaller-wins."""

from __future__ import annotations

from jarvis.voice.limits import (
    MAX_AUDIO_BYTES_CEILING,
    MAX_TEXT_CHARS_CEILING,
    MAX_TURNS_PER_SESSION_CEILING,
    default_limits,
    resolve_limits,
)


def test_defaults() -> None:
    limits = default_limits()
    assert limits.max_audio_bytes <= MAX_AUDIO_BYTES_CEILING
    assert limits.max_text_chars <= MAX_TEXT_CHARS_CEILING
    assert limits.wake_keyword == "jarvis"


def test_ceiling_clamps() -> None:
    limits = resolve_limits(max_audio_bytes=MAX_AUDIO_BYTES_CEILING * 10)
    assert limits.max_audio_bytes == MAX_AUDIO_BYTES_CEILING


def test_smaller_override_wins() -> None:
    limits = resolve_limits(max_text_chars=10, max_turns_per_session=2)
    assert limits.max_text_chars == 10
    assert limits.max_turns_per_session == 2


def test_turn_ceiling_clamps() -> None:
    limits = resolve_limits(max_turns_per_session=MAX_TURNS_PER_SESSION_CEILING * 5)
    assert limits.max_turns_per_session == MAX_TURNS_PER_SESSION_CEILING


def test_wake_keyword_normalized() -> None:
    assert resolve_limits(wake_keyword="  JARVIS  ").wake_keyword == "jarvis"
    assert resolve_limits(wake_keyword="").wake_keyword == "jarvis"
