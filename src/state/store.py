import asyncio

from .items import Items, parse_items
from src.events import EventBus, EventCode
from src.monitors import Monitor, MidasChargeMonitor


class GameState:
    def __init__(self, bus: EventBus):
        self._bus = bus
        self._data: dict | None = None
        self._version: int = 0
        self.items: Items | None = None
        self._monitors: list[Monitor] = []
        self._register_monitors()

    def _register_monitors(self) -> None:
        self._monitors.append(MidasChargeMonitor(self._bus))

    def _register_monitor(self, monitor: Monitor) -> None:
        self._monitors.append(monitor)

    def get(self) -> dict | None:
        return self._data

    async def set(self, data: dict):
        # store a copy to avoid accidental mutation
        self._data = data.copy()
        self._version += 1
        self.items = parse_items(data["items"]) if "items" in data else None
        await self._on_update()
        await self._bus.emit(EventCode.STATE_UPDATED, state=self)

    def version(self) -> int:
        return self._version

    async def _on_update(self) -> None:
        await asyncio.gather(*[monitor.update(self) for monitor in self._monitors])
