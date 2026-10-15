from __future__ import annotations

import asyncio

from src.lighting.controller import LightingController

RGBTuple = tuple[int, int, int]

# Map day/night is the baseline; no rule may sit at or below it.
MAP_PRIORITY = 0


class LightingArbiter:
    """Holds the active lighting requests and applies the winner once per update.

    Requests are keyed by priority (unique per rule, enforced by config) and
    persist until cleared. The highest priority wins. ``set`` / ``clear`` are
    synchronous and only mutate state — ``commit`` resolves the winner and
    queues it for the driver if it differs from what was last applied.
    """

    def __init__(self, controller: LightingController) -> None:
        self._controller = controller
        self._requests: dict[int, RGBTuple] = {}
        self._applied: RGBTuple | None = None
        self._queue: asyncio.Queue[RGBTuple] = asyncio.Queue()

    def set(self, priority: int, rgb: RGBTuple) -> None:
        self._requests[priority] = rgb

    def clear(self, priority: int) -> None:
        self._requests.pop(priority, None)

    def clear_all(self) -> None:
        self._requests.clear()

    def commit(self) -> None:
        if not self._requests:
            return
        rgb = self._requests[max(self._requests)]
        if rgb != self._applied:
            self._applied = rgb
            self._queue.put_nowait(rgb)

    async def run(self) -> None:
        while True:
            r, g, b = await self._queue.get()
            await self._controller.set_colour_rgb(r, g, b)
            self._queue.task_done()
