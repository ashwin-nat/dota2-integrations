from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.events import EventBus, EventCode

if TYPE_CHECKING:
    from src.state.store import GameState


class DayNightCycleMonitor:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._prev_daytime: Optional[bool] = None

    async def update(self, state: GameState) -> None:
        if not state.map:
            return

        if self._prev_daytime is None:
            self._prev_daytime = state.map.daytime
            if state.map.daytime:
                self._bus.emit(EventCode.DAYTIME_STARTED)
            else:
                self._bus.emit(EventCode.NIGHTTIME_STARTED, ns_night=state.map.nightstalker_night)

        elif self._prev_daytime != state.map.daytime:
            self._prev_daytime = state.map.daytime

            if state.map.daytime:
                self._bus.emit(EventCode.DAYTIME_STARTED)
            else:
                self._bus.emit(EventCode.NIGHTTIME_STARTED, ns_night=state.map.nightstalker_night)

        self._prev_daytime = state.map.daytime

    def clear(self) -> None:
        self._prev_daytime = None
