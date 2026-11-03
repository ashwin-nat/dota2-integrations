from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.rules.bus import RuleEventBus
    from src.state.map import MapState


class PeriodicMonitor:
    """Fires whenever the game clock passes a time t where t % period == offset % period.

    Clock time starts negative (pre-horn) but never goes backwards, so a trigger
    fires when it lies in (previous clock, current clock]. If a gap in updates
    spans several triggers, it fires once. Only triggers within
    [min_time, max_time] (clock seconds, both optional, inclusive) fire. The first update only records the
    clock, so joining mid-game does not fire for a past trigger.
    """

    def __init__(
        self,
        period: int,
        offset: int,
        event_key: str,
        bus: RuleEventBus,
        min_time: int | None = None,
        max_time: int | None = None,
    ) -> None:
        self._period = period
        self._offset = offset
        self._min_time = min_time  # triggers before this clock time are skipped
        self._max_time = max_time  # triggers after this clock time are skipped
        self._event_key = event_key
        self._bus = bus
        self._prev_clock: int | None = None

    def evaluate(self, map_state: MapState) -> None:
        clock = map_state.clock_time
        prev, self._prev_clock = self._prev_clock, clock
        if prev is None:
            return
        # Latest trigger at or before `clock`, capped at max_time (Python's % is
        # non-negative for a positive period)
        upper = clock if self._max_time is None else min(clock, self._max_time)
        latest = upper - ((upper - self._offset) % self._period)
        if latest > prev and (self._min_time is None or latest >= self._min_time):
            self._bus.emit(self._event_key)

    def clear(self) -> None:
        self._prev_clock = None
