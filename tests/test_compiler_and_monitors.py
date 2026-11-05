from types import SimpleNamespace

from src.rules import RulesConfig, compile_rules
from src.rules.actions import LightExecutor, SoundExecutor, WebhookExecutor
from src.rules.bus import EventBus
from src.rules.config import ActionType
from src.rules.monitor_base import StateSnapshot, StatefulMonitor


class FakeArbiter:
    def __init__(self):
        self.calls = []

    def set(self, priority, rgb):
        self.calls.append(("set", priority, rgb))

    def clear(self, priority):
        self.calls.append(("clear", priority))


def _light(priority, enabled=True):
    return {"type": "light", "r": 1, "g": 2, "b": 3, "priority": priority, "enabled": enabled}


def _webhook(enabled=True):
    return {"type": "webhook", "url": "http://localhost/x", "enabled": enabled}


def _setup(rules):
    arbiter = FakeArbiter()
    executors = {
        ActionType.LIGHT: LightExecutor(arbiter),
        ActionType.PLAY_SOUND: SoundExecutor(sound=None),
        ActionType.WEBHOOK: WebhookExecutor(),
    }
    bus = EventBus()
    config = RulesConfig.model_validate({"rules": rules})
    compiled = compile_rules(config.rules, bus, executors)
    return compiled, bus, arbiter, executors


def _hero_rule(rule_id, event, actions):
    return {"id": rule_id, "monitor": {"type": "hero", "event": event}, "actions": actions}


def _hero_snap(alive):
    return StateSnapshot(None, None, None, SimpleNamespace(alive=alive), None, None)


def test_one_monitor_per_rule_and_actions_on_the_right_executors():
    compiled, _, _, executors = _setup([
        _hero_rule("killed", "HERO_KILLED", [_light(5), _webhook()]),
        _hero_rule("respawned", "HERO_RESPAWNED", [_light(6)]),
    ])
    assert len(compiled.monitors) == 2
    assert compiled.counts() == {"hero": 2}
    assert sorted(executors[ActionType.LIGHT].keys()) == ["killed", "respawned"]
    assert list(executors[ActionType.WEBHOOK].keys()) == ["killed"]
    assert list(executors[ActionType.PLAY_SOUND].keys()) == []


def test_rules_without_enabled_actions_are_skipped():
    compiled, _, _, executors = _setup([
        _hero_rule("off", "HERO_KILLED", [_light(5, enabled=False)]),
        _hero_rule("empty", "HERO_RESPAWNED", []),
    ])
    assert compiled.monitors == []
    assert list(executors[ActionType.LIGHT].keys()) == []


def test_disabled_actions_are_not_registered():
    _, _, _, executors = _setup([_hero_rule("mixed", "HERO_KILLED", [_light(5, enabled=False), _webhook()])])
    assert list(executors[ActionType.LIGHT].keys()) == []
    assert list(executors[ActionType.WEBHOOK].keys()) == ["mixed"]


def test_end_to_end_each_action_runs_once_and_light_is_cleared_on_end():
    compiled, bus, arbiter, _ = _setup([_hero_rule("killed", "HERO_KILLED", [_light(5)])])
    compiled.evaluate_all(_hero_snap(True))   # first look: only records
    compiled.evaluate_all(_hero_snap(False))  # dies
    compiled.evaluate_all(_hero_snap(True))   # respawns
    assert arbiter.calls == [("set", 5, (1, 2, 3)), ("clear", 5)]


def test_clear_all_resets_monitors():
    compiled, _, arbiter, _ = _setup([_hero_rule("killed", "HERO_KILLED", [_light(5)])])
    compiled.evaluate_all(_hero_snap(True))
    compiled.clear_all()
    compiled.evaluate_all(_hero_snap(False))  # first look again after the reset: no fire
    assert arbiter.calls == []


def test_every_monitor_does_nothing_when_its_snapshot_part_is_missing():
    rules = [
        {"id": "i", "monitor": {"type": "item", "target": "item_bkb", "event": "COOLDOWN_READY"}, "actions": [_light(1)]},
        {"id": "bkb", "monitor": {"type": "item", "target": "item_black_king_bar", "event": "COOLDOWN_STARTED"}, "actions": [_light(2)]},
        {"id": "ib", "monitor": {"type": "item", "target": "item_blink", "event": "ITEM_LOST"}, "actions": [_light(3)]},
        {"id": "m", "monitor": {"type": "midas", "event": "CHARGED"}, "actions": [_light(4)]},
        {"id": "mo", "monitor": {"type": "midas", "event": "OVERCHARGED"}, "actions": [_light(5)]},
        {"id": "b", "monitor": {"type": "blink", "event": "COOLDOWN_STARTED"}, "actions": [_light(6)]},
        {"id": "h", "monitor": {"type": "hero", "event": "HERO_KILLED"}, "actions": [_light(7)]},
        {"id": "a", "monitor": {"type": "ability", "target": "x", "event": "COOLDOWN_STARTED"}, "actions": [_light(8)]},
        {"id": "p", "monitor": {"type": "periodic", "period": 30}, "actions": [_light(9)]},
        {"id": "mp", "monitor": {"type": "map", "event": "PAUSED"}, "actions": [{"type": "light", "r": 1, "g": 1, "b": 1}]},
    ]
    compiled, bus, arbiter, _ = _setup(rules)
    assert len(compiled.monitors) == len(rules)
    for monitor in compiled.monitors:
        if isinstance(monitor, StatefulMonitor):
            monitor._active = True  # even an active monitor must not end its state with no data
    compiled.evaluate_all(StateSnapshot(None, None, None, None, None, None))
    assert arbiter.calls == []


def test_two_rules_on_the_same_trigger_each_fire_their_own_actions_once():
    compiled, _, arbiter, _ = _setup([
        _hero_rule("first", "HERO_KILLED", [_light(5)]),
        _hero_rule("second", "HERO_KILLED", [_light(6)]),
    ])
    assert len(compiled.monitors) == 2
    compiled.evaluate_all(_hero_snap(True))
    compiled.evaluate_all(_hero_snap(False))
    assert sorted(arbiter.calls) == [("set", 5, (1, 2, 3)), ("set", 6, (1, 2, 3))]


def test_compile_skips_a_repeated_rule_id_and_keeps_the_first(caplog):
    # Followed friends' rules are compiled without RulesConfig's duplicate-id check
    first = RulesConfig.model_validate({"rules": [_hero_rule("same", "HERO_KILLED", [_light(5)])]}).rules
    second = RulesConfig.model_validate({"rules": [_hero_rule("same", "HERO_RESPAWNED", [_light(6)])]}).rules
    arbiter = FakeArbiter()
    executors = {
        ActionType.LIGHT: LightExecutor(arbiter),
        ActionType.PLAY_SOUND: SoundExecutor(sound=None),
        ActionType.WEBHOOK: WebhookExecutor(),
    }
    with caplog.at_level("WARNING"):
        compiled = compile_rules(first + second, EventBus(), executors)
    assert len(compiled.monitors) == 1
    assert "Skipping rule 'same'" in caplog.text
    compiled.evaluate_all(_hero_snap(True))
    compiled.evaluate_all(_hero_snap(False))  # the first rule (HERO_KILLED) is the one that was kept
    assert arbiter.calls == [("set", 5, (1, 2, 3))]
