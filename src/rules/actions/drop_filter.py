"""Adaptive drop filter: thins frequent sounds as match activity rises, never rare ones."""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class DropMode(StrEnum):
    GLOBAL = "global"        # one bucket for the whole match
    PER_EVENT = "per_event"  # each event's own bucket
    BLENDED = "blended"      # max of the two


class LeakyBucket:
    """A level that rises by 1 per trigger and drains exponentially with time constant `tau`."""

    def __init__(self, capacity: float, tau: float) -> None:
        self._capacity = capacity
        self._tau = tau
        self._level = 0.0
        self._updated: float | None = None

    def _drain(self, now: float) -> float:
        if self._updated is None:
            return 0.0
        elapsed = max(0.0, now - self._updated)
        return self._level * math.exp(-elapsed / self._tau)

    def fill(self, now: float) -> None:
        self._level = self._drain(now) + 1.0
        self._updated = now

    def level(self, now: float) -> float:
        return self._drain(now)

    def aggressiveness(self, now: float) -> float:
        return min(1.0, self.level(now) / self._capacity)


@dataclass
class _EventState:
    bucket: LeakyBucket
    last_seen: float | None = None
    interval: float = 0.0  # smoothed (EWMA) gap between triggers
    samples: int = 0       # measured gaps


class DropFilter:
    MODE = DropMode.GLOBAL
    GLOBAL_BUCKET_CAPACITY = 4
    EVENT_BUCKET_CAPACITY = 3
    GLOBAL_TAU_FACTOR = 0.11  # tau ~6.6 s at min_interval 60
    EVENT_TAU_FACTOR = 0.11
    INTERVAL_EWMA_ALPHA = 0.2
    MIN_SAMPLES = 2
    MIN_GAP_SECONDS = 0.05
    RECOVERY_FACTOR = 1.5       # a gap longer than this many learned intervals ends a burst
    RECOVERY_MIN_SECONDS = 6.0  # ...but only if it is at least this long, so jitter doesn't count
    MAX_SILENCE_SECONDS = 3.0   # if nothing has played for this long, the next trigger plays
    INTERVAL_RAMP = True
    DEBUG_LOG = False

    def __init__(
        self,
        drop_ratio: float,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._drop_ratio = min(1.0, max(0.0, float(drop_ratio)))
        self._min_interval = max(0.0, float(min_interval))
        self._clock = clock
        self._rng = rng
        self._lock = threading.Lock()
        self._reset_state()

    def _reset_state(self) -> None:
        self._global = LeakyBucket(self.GLOBAL_BUCKET_CAPACITY, self._tau(self.GLOBAL_TAU_FACTOR))
        self._events: dict[Hashable, _EventState] = {}
        self._last_played: float | None = None  # when any sound last got through

    def _tau(self, factor: float) -> float:
        return max(factor * self._min_interval, 1e-6)

    def reset(self) -> None:
        with self._lock:
            self._reset_state()

    def dump(self) -> str:
        """One-line description of the learned state, for debug logs only."""
        with self._lock:
            now = self._clock()
            events = ", ".join(
                f"{eid}[n={s.samples} int={s.interval:.1f}s lvl={s.bucket.level(now):.2f}"
                f" aggr={s.bucket.aggressiveness(now):.2f}]"
                for eid, s in self._events.items()
            )
            return (
                f"mode={self.MODE} ratio={self._drop_ratio} min_interval={self._min_interval} "
                f"global[lvl={self._global.level(now):.2f} aggr={self._global.aggressiveness(now):.2f}] "
                f"events: {events or 'none'}"
            )

    def should_allow(self, event_id: Hashable) -> bool:
        with self._lock:
            now = self._clock()
            allowed = self._decide(event_id, now)
            if not allowed and self._last_played is not None and now - self._last_played >= self.MAX_SILENCE_SECONDS:
                allowed = True  # thinned, never muted: nothing has played for too long
                self._log(now, event_id, 0.0, 0.0, True, "max silence")
            if allowed:
                self._last_played = now
            return allowed

    def _decide(self, event_id: Hashable, now: float) -> bool:
        state = self._events.get(event_id)
        if state is None:
            state = self._events[event_id] = _EventState(
                LeakyBucket(self.EVENT_BUCKET_CAPACITY, self._tau(self.EVENT_TAU_FACTOR))
            )

        # Aggressiveness is read before this trigger is counted
        aggressiveness = self._aggressiveness(state, now)

        gap: float | None = None
        if state.last_seen is not None:
            gap = max(now - state.last_seen, self.MIN_GAP_SECONDS)
            # A pause well past its usual rhythm ends the burst: forget the history and
            # relearn, instead of waiting for the buckets to drain
            if (state.samples >= self.MIN_SAMPLES and gap >= self.RECOVERY_MIN_SECONDS
                    and gap > self.RECOVERY_FACTOR * state.interval):
                state.samples = 0  # as if first seen: this trigger's gap is not a measurement
            elif state.samples == 0:
                state.interval = gap
                state.samples = 1
            else:
                state.interval += self.INTERVAL_EWMA_ALPHA * (gap - state.interval)
                state.samples += 1
        state.last_seen = now
        # Allowed or dropped, every trigger counts as demand
        self._global.fill(now)
        state.bucket.fill(now)

        if state.samples < self.MIN_SAMPLES:
            return self._log(now, event_id, aggressiveness, 0.0, True, "little history")
        if state.interval >= self._min_interval or (gap is not None and gap >= self._min_interval):
            return self._log(now, event_id, aggressiveness, 0.0, True, "rare")

        p = self._drop_ratio * aggressiveness
        if self.INTERVAL_RAMP:
            p *= 1.0 - state.interval / self._min_interval
        allowed = self._rng() >= p
        return self._log(now, event_id, aggressiveness, p, allowed, "roll")

    def _aggressiveness(self, state: _EventState, now: float) -> float:
        if self.MODE is DropMode.GLOBAL:
            return self._global.aggressiveness(now)
        if self.MODE is DropMode.PER_EVENT:
            return state.bucket.aggressiveness(now)
        return max(self._global.aggressiveness(now), state.bucket.aggressiveness(now))

    def _log(self, now: float, event_id: Hashable, aggressiveness: float, p: float,
             allowed: bool, why: str) -> bool:
        if self.DEBUG_LOG:
            logger.debug(
                f"drop_filter t={now:.2f} event={event_id!r} aggr={aggressiveness:.2f} "
                f"p={p:.2f} ({why}) -> {'allow' if allowed else 'drop'}"
            )
        return allowed
