from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Coroutine

from .codes import EventCode

Handler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self):
        self._handlers: dict[EventCode, list[Handler]] = defaultdict(list)

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

    async def emit(self, code: EventCode, **kwargs: Any) -> None:
        for handler in self._handlers[code]:
            await handler(**kwargs)


# Module-level singleton — import and use directly.
bus = EventBus()
