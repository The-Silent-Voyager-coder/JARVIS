"""In-process event bus.

Design (Phase 1 contract):

- Subscribers may be sync or async callables; the bus awaits them.
- Dispatch is strictly sequential and in subscription order, which preserves
  event ordering within a stream (TaskCreated → TaskStarted → ...).
- A failing subscriber is isolated: its error is logged and other subscribers
  still receive the event. The bus itself never raises from a handler.
- `close()` is graceful: it rejects further publishes and awaits nothing
  in flight (dispatch is synchronous, so a closed bus is quiescent).
- No external event framework; built on asyncio primitives.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from greatsage.events.models import Event
from greatsage.exceptions import EventError

log = logging.getLogger("greatsage.events.bus")

EventHandler = Callable[[Event], Awaitable[None] | None]


@dataclass(frozen=True)
class Subscription:
    id: str
    event_type: str | None  # None = receive all event types
    handler: EventHandler


class EventBus:
    """Publish/subscribe event bus with ordered, isolated dispatch."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._closed = False
        self._published: int = 0

    # --- subscription ---------------------------------------------------

    def subscribe(self, handler: EventHandler, event_type: str | None = None) -> Subscription:
        """Register a handler. `event_type=None` receives every event."""
        if self._closed:
            raise EventError("cannot subscribe: event bus is closed")
        sub = Subscription(id=uuid.uuid4().hex, event_type=event_type, handler=handler)
        self._subscriptions[sub.id] = sub
        return sub

    def unsubscribe(self, sub: Subscription | str) -> bool:
        """Remove a subscription (by object or id). Returns True if removed."""
        sub_id = sub.id if isinstance(sub, Subscription) else sub
        return self._subscriptions.pop(sub_id, None) is not None

    def clear(self) -> None:
        self._subscriptions.clear()

    # --- publication ----------------------------------------------------

    async def publish(self, event: Event) -> None:
        """Dispatch an event to matching subscribers, preserving order."""
        if self._closed:
            raise EventError("cannot publish: event bus is closed")
        self._published += 1
        for sub in tuple(self._subscriptions.values()):
            if sub.event_type is not None and sub.event_type != event.type:
                continue
            try:
                result = sub.handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # subscriber isolation
                log.error(
                    "event subscriber failed",
                    extra={"component": "events", "event_id": event.id, "event_type": event.type},
                )
                log.debug("subscriber error detail", exc_info=exc, extra={"component": "events"})

    def publish_nowait(self, event: Event) -> None:
        """Fire-and-forget publish from synchronous code (errors are logged)."""
        if self._closed:
            raise EventError("cannot publish: event bus is closed")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise EventError("no running event loop for publish_nowait") from exc
        loop.create_task(self.publish(event))

    # --- lifecycle ------------------------------------------------------

    async def close(self) -> None:
        """Reject further publishes/subscribes. Idempotent."""
        self._closed = True
        self._subscriptions.clear()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)

    @property
    def published_count(self) -> int:
        return self._published
