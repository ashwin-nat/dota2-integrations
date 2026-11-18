from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.rules.monitor_config import MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.config import Rule
    from src.state.abilities import Abilities
    from src.state.hero import HeroState
    from src.state.items import Items
    from src.state.map import MapState
    from src.state.player import PlayerState


@dataclass(frozen=True)
class StateSnapshot:
    """Everything a monitor can look at, built once per update by GameState.

    A part is None when the update did not carry it; each monitor returns early
    if the part it needs is missing.
    """
    items: Items | None
    prev_items: Items | None
    abilities: Abilities | None
    hero: HeroState | None
    player: PlayerState | None
    map: MapState | None


class Monitor(ABC):
    """Watches the game snapshot and publishes events on the bus."""

    type: MonitorType  # set by MonitorConfig.build; used for logs and the startup counts
    # Also evaluated during pre-game (clock -1:30 to the horn). Only monitors that read just the map clock.
    runs_before_horn: bool = False

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        self._rule = rule
        self._event_key = rule.id  # the bus key this monitor publishes under
        self._bus = bus
        self._seen_update = False

    def run(self, snap: StateSnapshot) -> None:
        """Evaluate one update. Events published during a monitor's first update since start or
        `reset()` are marked initial: the state was unknown before, so they report what is already
        true (starting items, day/night), not something that happened. Sounds skip them."""
        self._bus.initial = not self._seen_update
        self._seen_update = True
        try:
            self.evaluate(snap)
        finally:
            self._bus.initial = False

    def reset(self) -> None:
        """Clear per-match state and forget that an update was seen (on a match change)."""
        self._seen_update = False
        self.clear()

    @abstractmethod
    def evaluate(self, snap: StateSnapshot) -> None:
        """Look at one update and emit (or retract) events."""

    @abstractmethod
    def clear(self) -> None:
        """Reset per-match state (called on a match change)."""


class StatefulMonitor(Monitor):
    """Base for monitors that signal a state that begins and later ends.

    ``_fire`` emits the event when the state begins (actions run, light
    requests are set). ``_end`` retracts the event's light requests when the
    state ends; it is a no-op unless the monitor is currently active, so it is
    safe to call on every evaluation. ``clear`` resets per-match state.
    """

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
        self._active = False

    def _fire(self) -> None:
        self._active = True
        self._bus.emit(self._event_key)

    def _end(self) -> None:
        if self._active:
            self._active = False
            self._bus.retract(self._event_key)

    def clear(self) -> None:
        self._active = False


class TargetedStatefulMonitor(StatefulMonitor):
    """A stateful monitor that watches one named target (an item or ability name).

    The target comes from the rule's monitor config (`target`).
    """

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
        self._target: str = rule.monitor.target
