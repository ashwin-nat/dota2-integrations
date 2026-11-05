from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.rules.monitor_base import StateSnapshot, StatefulMonitor
from src.rules.monitor_config import MonitorConfig, MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus


class HeroMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.HERO]
    event: Literal["HERO_KILLED", "HERO_RESPAWNED"]

    def _create(self, bus: EventBus, key: str) -> HeroMonitor:
        return HeroMonitor(self.event, key, bus)


class HeroMonitor(StatefulMonitor):
    """Watches hero alive transitions and emits events.

    HERO_KILLED is active while the hero is dead, HERO_RESPAWNED while alive.
    """

    def __init__(self, event: str, event_key: str, bus: EventBus) -> None:
        super().__init__(event_key, bus)
        self._event = event
        self._prev_alive: bool | None = None

    def evaluate(self, snap: StateSnapshot) -> None:
        hero = snap.hero
        if hero is None:
            return
        alive = hero.alive
        if alive is None:
            return

        in_state = (not alive) if self._event == "HERO_KILLED" else alive
        if in_state:
            if self._prev_alive is not None and self._prev_alive != alive:
                self._fire()
        else:
            self._end()

        self._prev_alive = alive

    def clear(self) -> None:
        super().clear()
        self._prev_alive = None
