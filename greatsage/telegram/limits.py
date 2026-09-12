"""Telegram bridge limits (bounded polls, no daemon)."""

from __future__ import annotations

POLL_TIMEOUT_SECONDS_DEFAULT = 20.0
POLL_TIMEOUT_SECONDS_CEILING = 50.0

MAX_LISTEN_SECONDS_DEFAULT = 600.0
MAX_LISTEN_SECONDS_CEILING = 3600.0
