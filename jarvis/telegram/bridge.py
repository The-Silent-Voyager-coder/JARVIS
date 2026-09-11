"""Command dispatcher for Telegram chats (no AI calls in v1).

Only allowlisted chat ids get replies; everyone else is ignored silently
(no oracle, no error text back to strangers). Commands are plain text:
`/briefing`, `/status`, `/help`. Anything else gets the help text.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

HELP_TEXT = (
    "J.A.R.V.I.S. remote — commands:\n"
    "/briefing — health + recent episodes + open tasks/plans\n"
    "/status — overall health in one line\n"
    "/screenshot — current laptop screen (needs --content on listen)\n"
    "/help — this text"
)

# A handler may answer text, or {"photo": bytes, "caption": str}.
Reply = str | dict[str, object]


class TelegramBridge:
    """Routes one chat message to one reply (or None = ignore)."""

    def __init__(
        self,
        *,
        allowed_chat_ids: frozenset[int],
        getters: Mapping[str, Callable[[], Reply]] | None = None,
    ) -> None:
        self._allowed = allowed_chat_ids
        self._getters = dict(getters or {})

    @property
    def allowed_chat_ids(self) -> frozenset[int]:
        return self._allowed

    def handle(self, chat_id: int, text: str) -> Reply | None:
        if chat_id not in self._allowed:
            return None
        command = text.strip().split()[0].lower() if text.strip() else ""
        command = command.split("@")[0]
        if command in ("/start", "/help"):
            return HELP_TEXT
        if command in ("/briefing", "/status", "/screenshot"):
            name = command[1:]
            getter = self._getters.get(name)
            if getter is None:
                return f"{name} is not wired on this host."
            return getter()
        return f"unknown command {command.split()[0][:32]!r}.\n{HELP_TEXT}"
