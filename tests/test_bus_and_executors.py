import asyncio

from src.lighting.arbiter import MAP_PRIORITY
from src.rules.actions import ActionBinding, LightExecutor, SoundExecutor
from src.rules.bus import Event, EventBus, EventType
from src.rules.config import LightAction, PlaySoundAction
from src.rules.monitor_config import MonitorType


def test_bus_runs_handlers_in_order_with_times():
    bus, seen = EventBus(), []
    bus.subscribe("k", lambda e: seen.append(("a", e)))
    bus.subscribe("k", lambda e: seen.append(("b", e)))
    bus.game_time, bus.clock_time = 10, -5
    bus.emit("k")
    assert [name for name, _ in seen] == ["a", "b"]
    assert seen[0][1] == Event("k", EventType.STARTED, 10, -5)


def test_bus_retract_publishes_ended():
    bus, seen = EventBus(), []
    bus.subscribe("k", seen.append)
    bus.retract("k")
    assert seen[0].type is EventType.ENDED


def test_bus_failing_handler_does_not_stop_others():
    bus, seen = EventBus(), []

    def boom(_):
        raise RuntimeError("boom")

    bus.subscribe("k", boom)
    bus.subscribe("k", seen.append)
    bus.emit("k")
    assert len(seen) == 1


def test_bus_unsubscribed_key_is_ignored():
    EventBus().emit("nobody")


class FakeArbiter:
    def __init__(self):
        self.calls = []

    def set(self, priority, rgb):
        self.calls.append(("set", priority, rgb))

    def clear(self, priority):
        self.calls.append(("clear", priority))


def _light(rule_id, priority):
    action = LightAction(type="light", r=1, g=2, b=3, priority=priority)
    return ActionBinding(rule_id, MonitorType.ITEM, "COOLDOWN_READY", action)


def test_light_executor_started_and_ended():
    arbiter = FakeArbiter()
    ex = LightExecutor(arbiter)
    ex.register("k", _light("r1", 5))
    ex.on_event(Event("k", EventType.STARTED, 1, 1))
    ex.on_event(Event("k", EventType.ENDED, 2, 2))
    assert arbiter.calls == [("set", 5, (1, 2, 3)), ("clear", 5)]


def test_light_executor_map_rule_uses_map_priority_and_ignores_ended():
    arbiter = FakeArbiter()
    ex = LightExecutor(arbiter)
    ex.register("k", _light("map", None))
    ex.on_event(Event("k", EventType.STARTED, 1, 1))
    ex.on_event(Event("k", EventType.ENDED, 2, 2))
    assert arbiter.calls == [("set", MAP_PRIORITY, (1, 2, 3))]


def test_executor_only_reacts_to_its_own_keys():
    arbiter = FakeArbiter()
    ex = LightExecutor(arbiter)
    ex.register("k", _light("r1", 5))
    ex.on_event(Event("other", EventType.STARTED, 1, 1))
    assert arbiter.calls == []
    assert list(ex.keys()) == ["k"]


def _sound(rule_id):
    action = PlaySoundAction(type="play_sound", clips=[{"file": "x.mp3", "probability": 100}])
    return ActionBinding(rule_id, MonitorType.HERO, "HERO_KILLED", action)


class FakeSound:
    def __init__(self):
        self.played = []

    async def play(self, file, volume=1.0):
        self.played.append(file)


async def _run_drain(ex, events, settle=0.05):
    for e in events:
        ex.on_event(e)
    task = asyncio.create_task(ex._drain())
    await asyncio.sleep(settle)
    task.cancel()


def test_sound_executor_plays_below_burst_limit_and_ignores_ended():
    sound = FakeSound()
    ex = SoundExecutor(sound)
    ex.register("k", _sound("r1"))
    asyncio.run(_run_drain(ex, [Event("k", EventType.STARTED, 1, 1), Event("k", EventType.ENDED, 2, 2)]))
    assert sound.played == ["x.mp3"]


def test_sound_executor_drops_burst():
    sound = FakeSound()
    ex = SoundExecutor(sound)
    for i in range(3):
        ex.register("k", _sound(f"r{i}"))
    asyncio.run(_run_drain(ex, [Event("k", EventType.STARTED, 1, 1)]))
    assert sound.played == []


def test_sound_worker_survives_a_failing_play():
    class Flaky(FakeSound):
        async def play(self, file, volume=1.0):
            if not self.played and not getattr(self, "failed", False):
                self.failed = True
                raise RuntimeError("audio device error")
            await super().play(file, volume)

    sound = Flaky()
    ex = SoundExecutor(sound)
    ex.register("k", _sound("r1"))

    async def scenario():
        task = asyncio.create_task(ex._drain())
        ex.on_event(Event("k", EventType.STARTED, 1, 1))
        await asyncio.sleep(0.05)
        ex.on_event(Event("k", EventType.STARTED, 2, 2))
        await asyncio.sleep(0.05)
        alive = not task.done()
        task.cancel()
        return alive

    assert asyncio.run(scenario())
    assert sound.played == ["x.mp3"]


def test_bus_history_is_off_by_default():
    bus = EventBus()
    bus.emit("a")
    assert bus.published == 1
    assert bus.history is None


def test_bus_records_history_when_enabled():
    bus = EventBus(history_size=10)
    bus.game_time, bus.clock_time = 5, -2
    bus.emit("a")
    bus.retract("a")
    assert bus.published == 2
    assert [(e.key, e.type) for e in bus.history] == [("a", EventType.STARTED), ("a", EventType.ENDED)]
