import asyncio

from .items import Items, parse_items
from src.events import EventBus, EventCode
from src.monitors import Monitor, MidasMonitor


class GameState:
    def __init__(self, bus: EventBus):
        self._bus = bus
        self._data: dict | None = None
        self._version: int = 0
        self._match_id: str | None = None
        self.items: Items | None = None
        self._monitors: list[Monitor] = []
        self._register_monitors()

    def _register_monitors(self) -> None:
        self._monitors.append(MidasMonitor(self._bus))

    def _register_monitor(self, monitor: Monitor) -> None:
        self._monitors.append(monitor)

    def get(self) -> dict | None:
        return self._data

    async def set(self, data: dict):
        # store a copy to avoid accidental mutation
        self._data = data.copy()
        self._version += 1
        match_id = data.get("map", {}).get("matchid")
        if match_id != self._match_id:
            self._match_id = match_id
            self._clear_monitors()
        self.items = parse_items(data["items"]) if "items" in data else None
        await self._on_update()
        self._bus.emit(EventCode.STATE_UPDATED, state=self)

    def version(self) -> int:
        return self._version

    def _clear_monitors(self) -> None:
        for monitor in self._monitors:
            monitor.clear()

    async def _on_update(self) -> None:
        await asyncio.gather(*[monitor.update(self) for monitor in self._monitors])
