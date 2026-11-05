from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from src.rules.monitor_base import Monitor, StateSnapshot
from src.rules.monitor_config import MonitorConfig, MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus


class PeriodicMonitorConfig(MonitorConfig):
    """Fires every `period` seconds of game clock, shifted by `offset` seconds."""
    type: Literal[MonitorType.PERIODIC]
    period: int = Field(ge=1)
    offset: int = Field(ge=-59, le=59, default=0)
    # Game clock seconds (may be negative); only triggers inside [min_time, max_time] fire
    min_time: int | None = None
    max_time: int | None = None

    @model_validator(mode="after")
    def min_must_not_exceed_max(self) -> PeriodicMonitorConfig:
        if self.min_time is not None and self.max_time is not None and self.min_time > self.max_time:
            raise ValueError(f"min_time ({self.min_time}) cannot be greater than max_time ({self.max_time})")
        return self

    @property
    def event(self) -> str:
        return "TICK"

    def _create(self, bus: EventBus, key: str) -> PeriodicMonitor:
        return PeriodicMonitor(self.period, self.offset, key, bus, self.min_time, self.max_time)


class PeriodicMonitor(Monitor):
    """Fires whenever the game clock passes a time t where t % period == offset % period.

    Clock time starts negative (pre-horn) but never goes backwards, so a trigger
    fires when it lies in (previous clock, current clock]. If a gap in updates
    spans several triggers, it fires once. Only triggers within
    [min_time, max_time] (clock seconds, both optional, inclusive) fire. The first update only records the
    clock, so joining mid-game does not fire for a past trigger.
    """

    runs_before_horn = True

    def __init__(
        self,
        period: int,
        offset: int,
        event_key: str,
        bus: EventBus,
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

    def evaluate(self, snap: StateSnapshot) -> None:
        if snap.map is None:
            return
        clock = snap.map.clock_time
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


class OnceMonitorConfig(MonitorConfig):
    """Fires a single time per match, when the game clock reaches `time` seconds (may be negative)."""
    type: Literal[MonitorType.ONCE]
    time: int

    @property
    def event(self) -> str:
        return "TICK"

    def _create(self, bus: EventBus, key: str) -> OnceMonitor:
        return OnceMonitor(self.time, key, bus)


class OnceMonitor(Monitor):
    """Fires when the game clock passes `time`: time lies in (previous clock, current clock].

    The clock never goes backwards within a match, so this fires at most once. The
    first update only records the clock, so joining after `time` does not fire.
    """

    runs_before_horn = True

    def __init__(self, time: int, event_key: str, bus: EventBus) -> None:
        self._time = time
        self._event_key = event_key
        self._bus = bus
        self._prev_clock: int | None = None

    def evaluate(self, snap: StateSnapshot) -> None:
        if snap.map is None:
            return
        clock = snap.map.clock_time
        prev, self._prev_clock = self._prev_clock, clock
        if prev is not None and prev < self._time <= clock:
            self._bus.emit(self._event_key)

    def clear(self) -> None:
        self._prev_clock = None
