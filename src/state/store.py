import asyncio

from .items import Items, BaseItem, parse_items
from .map import MapState, parse_map
from src.events import EventBus, EventCode
from src.monitors import Monitor, MidasMonitor, DayNightCycleMonitor


class GameState:
    def __init__(self, bus: EventBus):
        self._bus = bus
        self._data: dict | None = None
        self._version: int = 0
        self.items: Items | None = None
        self.map: MapState | None = None
        self._monitors: list[Monitor] = []
        self._register_monitors()

        # Rule-engine state — populated by set_compiled_rules()
        from src.rules.compiler import CompiledRules
        self._compiled_rules: CompiledRules | None = None
        self._prev_items: dict[str, BaseItem] = {}  # slot_id → previous item

    def _register_monitors(self) -> None:
        self._monitors.append(MidasMonitor(self._bus))
        self._monitors.append(DayNightCycleMonitor(self._bus))

    def _register_monitor(self, monitor: Monitor) -> None:
        self._monitors.append(monitor)

    def set_compiled_rules(self, compiled_rules) -> None:
        """Attach precompiled rule monitors. Called once at startup."""
        self._compiled_rules = compiled_rules

    def get(self) -> dict | None:
        return self._data

    async def set(self, data: dict):
        # store a copy to avoid accidental mutation
        self._data = data.copy()
        self._version += 1
        self.items = parse_items(data["items"]) if "items" in data else None
        new_map = parse_map(data["map"]) if "map" in data else None
        self._handle_match_change(new_map)
        self.map = new_map
        await self._on_update()
        self._bus.emit(EventCode.STATE_UPDATED, state=self)

    def version(self) -> int:
        return self._version

    def _handle_match_change(self, new_map: MapState | None) -> None:
        old_id = self.map.matchid if self.map else None
        new_id = new_map.matchid if new_map else None
        if new_id != old_id:
            self._clear_monitors()
            self._prev_items.clear()
            print(f"Match changed from {old_id} to {new_id}")

    def _clear_monitors(self) -> None:
        for monitor in self._monitors:
            monitor.clear()
        if self._compiled_rules:
            for monitors in self._compiled_rules.monitors_by_item.values():
                for m in monitors:
                    m.clear()

    async def _on_update(self) -> None:
        await asyncio.gather(*[monitor.update(self) for monitor in self._monitors])
        self._run_rule_monitors()

    def _run_rule_monitors(self) -> None:
        if not self._compiled_rules or not self.items:
            return

        monitors_by_item = self._compiled_rules.monitors_by_item

        for item in self.items:
            monitors = monitors_by_item.get(item.name)
            if not monitors:
                continue
            prev = self._prev_items.get(item.slot_id)
            for monitor in monitors:
                monitor.evaluate(item, prev)

        # Snapshot current items for next update
        self._prev_items = {item.slot_id: item for item in self.items}
