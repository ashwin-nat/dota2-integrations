from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    STARTED = "started"  # the state began, or a one-off event happened
    ENDED = "ended"      # the state ended (only for stateful monitors)


@dataclass(frozen=True)
class Event:
    key: str
    type: EventType
    game_time: int | None
    clock_time: int | None


Handler = Callable[[Event], None]  # plain function: must not block or await


class EventBus:
    """Synchronous topic router. Knows nothing about actions, lights or queues."""

    def __init__(self, history_size: int = 0) -> None:
        """`history_size` > 0 keeps that many recent events for debugging (--debug); 0 keeps none."""
        self._subscribers: dict[str, list[Handler]] = {}
        # Stamped onto events; GameState sets both on each update, before monitors run.
        self.game_time: int | None = None
        self.clock_time: int | None = None  # negative before the horn
        self.published = 0  # total events published
        self.history: deque[Event] | None = deque(maxlen=history_size) if history_size > 0 else None

    def subscribe(self, key: str, handler: Handler) -> None:
        """Register a handler for a key. Startup only; handlers run in subscription order."""
        self._subscribers.setdefault(key, []).append(handler)

    def emit(self, key: str) -> None:
        """Publish a STARTED event: the state began, or a one-off event happened."""
        self._publish(key, EventType.STARTED)

    def retract(self, key: str) -> None:
        """Publish an ENDED event: the state signalled by an earlier emit has ended."""
        self._publish(key, EventType.ENDED)

    def _publish(self, key: str, type_: EventType) -> None:
        event = Event(key, type_, self.game_time, self.clock_time)
        self.published += 1
        if self.history is not None:
            self.history.append(event)
        handlers = self._subscribers.get(key)
        if not handlers:
            return
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # One broken executor must not stop the others or break the tick
                logger.exception(f"Handler failed for {type_} event {key!r}")
