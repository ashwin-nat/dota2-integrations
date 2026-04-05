from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.rules.bus import RuleEventBus
    from src.state.map import MapState


class MapMonitor:
    """Watches map state transitions and emits rule-bus events.

    Each instance handles one event type (DAYTIME_STARTED or NIGHTTIME_STARTED).
    """

    def __init__(self, event: str, event_key: str, bus: RuleEventBus) -> None:
        self._event = event
        self._event_key = event_key
        self._bus = bus
        self._prev_daytime: bool | None = None

    def evaluate(self, map_state: MapState) -> None:
        daytime = map_state.daytime

        if self._prev_daytime is None:
            # First tick — emit initial state
            self._prev_daytime = daytime
            self._maybe_emit(daytime, is_initial=True)
            return

        if self._prev_daytime != daytime:
            self._prev_daytime = daytime
            self._maybe_emit(daytime, is_initial=False)

    def _maybe_emit(self, daytime: bool, is_initial: bool) -> None:
        if self._event == "DAYTIME_STARTED" and daytime:
            self._bus.emit(self._event_key)
        elif self._event == "NIGHTTIME_STARTED" and not daytime:
            self._bus.emit(self._event_key)

    def clear(self) -> None:
        self._prev_daytime = None
