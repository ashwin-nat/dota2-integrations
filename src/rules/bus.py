from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from src.rules.config import AnyAction, MonitorType


@dataclass
class EventContext:
    """Metadata attached to a fired rule event, passed through to action executors."""
    rule_id: str
    monitor_type: MonitorType
    event_name: str
    data: dict[str, Any] = field(default_factory=dict)


ActionExecutorFn = Callable[[list[AnyAction], EventContext], Coroutine[Any, Any, None]]


class RuleEventBus:
    """Minimal async event bus for rule-compiled string-key events.

    Events are plain strings (e.g. "ITEM.COOLDOWN_READY.item_blink").
    Listeners are precompiled lists of typed Action models.
    No routing logic, no enums, no filtering at runtime.
    """

    def __init__(self, executor: ActionExecutorFn) -> None:
        self._listeners: dict[str, list[AnyAction]] = {}
        self._contexts: dict[str, EventContext] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._executor = executor

    def register(self, event_key: str, actions: list[AnyAction], context: EventContext) -> None:
        """Called at compile time only — never at runtime."""
        self._listeners.setdefault(event_key, []).extend(actions)
        self._contexts[event_key] = context

    def emit(self, event_key: str) -> None:
        """Non-blocking: queue the event for async dispatch."""
        self._queue.put_nowait(event_key)

    async def process_forever(self) -> None:
        while True:
            event_key = await self._queue.get()
            actions = self._listeners.get(event_key, [])
            ctx = self._contexts.get(event_key)
            if actions and ctx is not None:
                await self._executor(actions, ctx)
            self._queue.task_done()
