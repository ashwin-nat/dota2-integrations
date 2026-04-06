from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.rules.bus import RuleEventBus
    from src.state.hero import HeroState


class HeroMonitor:
    """Watches hero alive transitions and emits rule-bus events."""

    def __init__(self, event: str, event_key: str, bus: RuleEventBus) -> None:
        self._event = event
        self._event_key = event_key
        self._bus = bus
        self._prev_alive: bool | None = None

    def evaluate(self, hero: HeroState) -> None:
        alive = hero.alive
        if alive is None:
            return

        if self._prev_alive is not None and self._prev_alive != alive:
            if self._event == "HERO_KILLED" and not alive:
                self._bus.emit(self._event_key)
            elif self._event == "HERO_RESPAWNED" and alive:
                self._bus.emit(self._event_key)

        self._prev_alive = alive

    def clear(self) -> None:
        self._prev_alive = None
