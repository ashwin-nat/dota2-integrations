from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from src.rules.config import AnyAction

ActionExecutorFn = Callable[[list[AnyAction]], Coroutine[Any, Any, None]]


class RuleEventBus:
    """Minimal async event bus for rule-compiled string-key events.

    Events are plain strings (e.g. "ITEM.COOLDOWN_READY.item_blink").
    Listeners are precompiled lists of typed Action models.
    No routing logic, no enums, no filtering at runtime.
    """

    def __init__(self, executor: ActionExecutorFn) -> None:
        self._listeners: dict[str, list[AnyAction]] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._executor = executor

    def register(self, event_key: str, actions: list[AnyAction]) -> None:
        """Called at compile time only — never at runtime."""
        self._listeners.setdefault(event_key, []).extend(actions)

    def emit(self, event_key: str) -> None:
        """Non-blocking: queue the event for async dispatch."""
        self._queue.put_nowait(event_key)

    async def process_forever(self) -> None:
        while True:
            event_key = await self._queue.get()
            actions = self._listeners.get(event_key, [])
            if actions:
                await self._executor(actions)
            self._queue.task_done()
