from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Literal

from src.rules.monitor_base import Monitor, StateSnapshot
from src.rules.monitor_config import MonitorConfig, MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.config import Rule


class MapMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.MAP]
    event: Literal["DAYTIME_STARTED", "NIGHTTIME_STARTED", "PAUSED", "UNPAUSED"]

    takes_light_priority: ClassVar[bool] = False  # map rules are the baseline colour

    def _create(self, bus: EventBus, rule: Rule) -> MapMonitor:
        return MapMonitor(rule, bus)


class MapMonitor(Monitor):
    """Watches map state transitions and emits events.

    Each instance handles one map-level event type.
    """

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
        self._event: str = rule.monitor.event
        self._prev_daytime: bool | None = None
        self._prev_paused: bool | None = None

    def evaluate(self, snap: StateSnapshot) -> None:
        map_state = snap.map
        if map_state is None:
            return
        daytime = map_state.daytime
        paused = map_state.paused

        if self._prev_daytime is None or self._prev_paused is None:
            # First tick — emit initial state for the selected event
            self._prev_daytime = daytime
            self._prev_paused = paused
            self._maybe_emit(daytime, paused, is_initial=True)
            return

        if self._event in {"DAYTIME_STARTED", "NIGHTTIME_STARTED"}:
            if self._prev_daytime != daytime:
                self._prev_daytime = daytime
                self._maybe_emit(daytime, paused, is_initial=False)
        elif self._event in {"PAUSED", "UNPAUSED"}:
            if self._prev_paused != paused:
                self._prev_paused = paused
                self._maybe_emit(daytime, paused, is_initial=False)

    def _maybe_emit(self, daytime: bool, paused: bool, is_initial: bool) -> None:
        # Day/night report their starting state (the light colour needs it); a pause
        # event means the game *changed* to that state, so nothing fires on the first look.
        if is_initial and self._event in {"PAUSED", "UNPAUSED"}:
            return
        if self._event == "DAYTIME_STARTED" and daytime:
            self._bus.emit(self._event_key)
        elif self._event == "NIGHTTIME_STARTED" and not daytime:
            self._bus.emit(self._event_key)
        elif self._event == "PAUSED" and paused:
            self._bus.emit(self._event_key)
        elif self._event == "UNPAUSED" and not paused:
            self._bus.emit(self._event_key)

    def clear(self) -> None:
        self._prev_daytime = None
        self._prev_paused = None
