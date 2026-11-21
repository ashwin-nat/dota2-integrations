import random

import pytest

from src.rules.actions.drop_filter import DropFilter, DropMode, LeakyBucket


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def make(drop_ratio=0.5, min_interval=30, mode=DropMode.GLOBAL, seed=1):
    clock = Clock()
    rng = random.Random(seed)
    flt = DropFilter(drop_ratio, min_interval, clock=clock, rng=rng.random)
    return flt, clock


def run(flt, clock, event, period, count):
    """Trigger `event` every `period` seconds; return the allow results."""
    out = []
    for _ in range(count):
        out.append(flt.should_allow(event))
        clock.t += period
    return out


def test_bucket_drains_exponentially():
    b = LeakyBucket(capacity=10, tau=10)
    b.fill(0)
    b.fill(0)
    assert b.level(0) == 2
    assert b.level(10) == pytest.approx(2 / 2.718281828, rel=1e-6)
    assert b.aggressiveness(0) == 0.2


def test_first_triggers_are_allowed():
    flt, clock = make(drop_ratio=1.0)
    assert run(flt, clock, "a", 1, 2) == [True, True]  # fewer than MIN_SAMPLES gaps


def test_unfiltered_never_drops():
    flt, clock = make(drop_ratio=0.0, min_interval=0)
    assert all(run(flt, clock, "a", 1, 200))
    flt, clock = make(drop_ratio=0.0, min_interval=30)
    assert all(run(flt, clock, "a", 1, 200))


def test_rare_events_are_never_dropped():
    flt, clock = make(drop_ratio=1.0, min_interval=30)
    assert all(run(flt, clock, "rare", 40, 100))


def test_frequent_events_ramp_up_and_drop_at_most_the_ratio():
    flt, clock = make(drop_ratio=0.5, min_interval=30)
    results = run(flt, clock, "busy", 1, 400)
    assert all(results[:2])  # too little history: the first triggers always play
    drops = results.count(False)
    assert drops > 0
    assert drops / len(results) <= 0.5


def test_drops_cool_down_after_a_lull():
    flt, clock = make(drop_ratio=1.0, min_interval=30)
    run(flt, clock, "busy", 1, 200)
    clock.t += 3000
    # The bucket has drained, so the next triggers are allowed again
    assert flt.should_allow("busy")


def test_per_event_mode_ignores_other_events():
    class PerEvent(DropFilter):
        MODE = DropMode.PER_EVENT

    clock = Clock()
    flt = PerEvent(1.0, 30, clock=clock, rng=random.Random(1).random)
    run(flt, clock, "noisy", 0.5, 200)
    # A newly active clip starts unthrottled even though the match is hot
    assert flt.should_allow("fresh")


def test_reset_clears_state():
    flt, clock = make(drop_ratio=1.0, min_interval=30)
    run(flt, clock, "busy", 1, 200)
    flt.reset()
    assert run(flt, clock, "busy", 1, 2) == [True, True]


def test_values_are_clamped():
    flt, clock = make(drop_ratio=5, min_interval=-3)
    assert all(run(flt, clock, "a", 1, 50))  # min_interval 0: everything is rare


def test_a_pause_past_the_usual_rhythm_ends_the_burst():
    flt, clock = make(drop_ratio=1.0, min_interval=60)
    run(flt, clock, "busy", 4, 100)  # hot, learned interval ~4 s
    clock.t += 3  # 7 s since the last trigger: more than 1.5 x 4 s
    assert flt.should_allow("busy")
    # Relearning: the next couple of triggers are still allowed
    assert run(flt, clock, "busy", 4, 1) == [True]


def test_a_burst_is_thinned_but_never_muted():
    flt, clock = make(drop_ratio=1.0, min_interval=60)
    last_played = None
    longest = 0.0
    for _ in range(400):
        for ev in ("a", "b"):
            if flt.should_allow(ev):
                if last_played is not None:
                    longest = max(longest, clock.t - last_played)
                last_played = clock.t
            clock.t += 0.8
    assert longest <= DropFilter.MAX_SILENCE_SECONDS + 0.8
