from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

from .codes import EventCode

Handler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self):
        self._handlers: dict[EventCode, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[tuple[EventCode, dict[str, Any]]] = asyncio.Queue()

    def on(self, *codes: EventCode) -> Callable[[Handler], Handler]:
        """Decorator to register an async handler for one or more event codes.

        Usage::

            @bus.on(EventCode.MIDAS_CHARGED)
            async def handle(slot_id: str, charges: int):
                ...
        """
        def decorator(fn: Handler) -> Handler:
            for code in codes:
                self._handlers[code].append(fn)
            return fn
        return decorator

    def emit(self, code: EventCode, **kwargs: Any) -> None:
        """Non-blocking: put an event on the queue for async processing."""
        self._queue.put_nowait((code, kwargs))

    async def _handle(self, code: EventCode, **kwargs: Any) -> None:
        for handler in self._handlers[code]:
            await handler(**kwargs)

    async def process_forever(self) -> None:
        """Drain the queue indefinitely, dispatching each event to its handlers."""
        while True:
            code, kwargs = await self._queue.get()
            await self._handle(code, **kwargs)
            self._queue.task_done()
