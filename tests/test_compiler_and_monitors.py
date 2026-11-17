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


def _clock_snap(clock):
    return StateSnapshot(None, None, None, None, None, SimpleNamespace(clock_time=clock))


def _once_rule(time):
    return {"id": "once", "monitor": {"type": "once", "time": time}, "actions": [_light(1)]}


def test_once_fires_a_single_time_when_the_clock_reaches_it():
    compiled, _, arbiter, _ = _setup([_once_rule(300)])
    for clock in (298, 299, 300, 301, 302):
        compiled.evaluate_all(_clock_snap(clock))
    assert arbiter.calls == [("set", 1, (1, 2, 3))]


def test_once_fires_when_a_gap_in_updates_skips_past_it():
    compiled, _, arbiter, _ = _setup([_once_rule(300)])
    compiled.evaluate_all(_clock_snap(290))
    compiled.evaluate_all(_clock_snap(310))
    assert len(arbiter.calls) == 1


def test_once_can_target_before_the_horn():
    compiled, _, arbiter, _ = _setup([_once_rule(-30)])
    compiled.evaluate_all(_clock_snap(-31))
    compiled.evaluate_all(_clock_snap(-30))
    assert len(arbiter.calls) == 1


def test_once_does_not_fire_when_joining_after_its_time():
    compiled, _, arbiter, _ = _setup([_once_rule(300)])
    compiled.evaluate_all(_clock_snap(300))
    compiled.evaluate_all(_clock_snap(301))
    assert arbiter.calls == []


def test_once_fires_again_in_the_next_match():
    compiled, _, arbiter, _ = _setup([_once_rule(300)])
    compiled.evaluate_all(_clock_snap(299))
    compiled.evaluate_all(_clock_snap(300))
    compiled.clear_all()
    arbiter.calls.clear()
    compiled.evaluate_all(_clock_snap(299))
    compiled.evaluate_all(_clock_snap(300))
    assert len(arbiter.calls) == 1


def _ability_snap(cooldown):
    from src.state.abilities import Abilities, Ability

    ability = Ability("ability1", "bristleback_quill_spray", 4, cooldown == 0, False, False,
                      cooldown, 0, False)
    return StateSnapshot(None, None, Abilities({"ability1": ability}), None, None, None)


def test_ability_recast_fires_without_a_zero_cooldown_frame():
    # Frames ~1 s apart and a 3 s cooldown: recasting at once reads 1 -> 3, never 0.
    compiled, bus, _, _ = _setup([
        {"id": "q", "monitor": {"type": "ability", "target": "bristleback_quill_spray",
                                "event": "COOLDOWN_STARTED"}, "actions": [_light(8)]},
    ])
    monitor = compiled.monitors[0]
    published = []
    bus.subscribe("q", lambda event: published.append(event))
    for cooldown in (0, 3, 2, 1, 3, 2, 1, 3):
        monitor.evaluate(_ability_snap(cooldown))
    starts = [e for e in published if e.type.name == "STARTED"]
    assert len(starts) == 3


def test_charge_based_ability_fires_when_a_charge_is_spent():
    # Shrapnel keeps cooldown at 0; casting only lowers `charges`, regen raises them.
    from src.state.abilities import Abilities, ChargeAbility

    def frame(charges):
        a = ChargeAbility("ability0", "sniper_shrapnel", 4, charges > 0, False, True, 0, 0, False,
                    charges, 3, 0 if charges == 3 else 20)
        return StateSnapshot(None, None, Abilities({"ability0": a}), None, None, None)

    frames = [frame(c) for c in (3, 3, 2, 2, 1, 2, 2, 3, 3, 2)]
    assert _ability_starts(["sniper_shrapnel"], frames) == {"sniper_shrapnel": 3}


def _slots_snap(*slots):
    """One frame of abilities from (name, cooldown) pairs, in slot order."""
    from src.state.abilities import Abilities, Ability

    return StateSnapshot(None, None, Abilities({
        f"ability{i}": Ability(f"ability{i}", name, 1, cd == 0, False, True, cd, 0, False)
        for i, (name, cd) in enumerate(slots)
    }), None, None, None)


def _ability_starts(targets, frames):
    """Run ability monitors for each target over the frames; return how often each fired."""
    compiled, bus, _, _ = _setup([
        {"id": t, "monitor": {"type": "ability", "target": t, "event": "COOLDOWN_STARTED"},
         "actions": [_light(10 + i)]}
        for i, t in enumerate(targets)
    ])
    counts = dict.fromkeys(targets, 0)
    for t in targets:
        bus.subscribe(t, lambda e, t=t: counts.__setitem__(t, counts[t] + (e.type.name == "STARTED")))
    for frame in frames:
        compiled.evaluate_all(frame)
    return counts


def test_invoker_eviction_does_not_fire_the_evicted_spell():
    # Invoked spells enter slot 3 and shift to slot 4; a third invoke evicts the oldest.
    orbs = [("invoker_quas", 0), ("invoker_wex", 0), ("invoker_exort", 0)]
    frames = [
        _slots_snap(*orbs, ("invoker_empty1", 0), ("invoker_empty2", 0), ("invoker_invoke", 0)),
        _slots_snap(*orbs, ("invoker_tornado", 0), ("invoker_empty1", 0), ("invoker_invoke", 0)),
        _slots_snap(*orbs, ("invoker_chaos_meteor", 0), ("invoker_tornado", 0), ("invoker_invoke", 0)),
        _slots_snap(*orbs, ("invoker_deafening_blast", 0), ("invoker_chaos_meteor", 0), ("invoker_invoke", 0)),
        _slots_snap(*orbs, ("invoker_ice_wall", 0), ("invoker_deafening_blast", 0), ("invoker_invoke", 0)),
    ]
    counts = _ability_starts(["invoker_tornado", "invoker_chaos_meteor", "invoker_deafening_blast"], frames)
    assert counts == {"invoker_tornado": 0, "invoker_chaos_meteor": 0, "invoker_deafening_blast": 0}


def test_invoker_spell_still_fires_when_cast_after_shifting_slots():
    orbs = [("invoker_quas", 0), ("invoker_wex", 0), ("invoker_exort", 0)]
    frames = [
        _slots_snap(*orbs, ("invoker_tornado", 0), ("invoker_empty1", 0)),
        _slots_snap(*orbs, ("invoker_chaos_meteor", 0), ("invoker_tornado", 0)),
        _slots_snap(*orbs, ("invoker_chaos_meteor", 0), ("invoker_tornado", 30)),
    ]
    assert _ability_starts(["invoker_tornado"], frames) == {"invoker_tornado": 1}


KEZ_KATANA = [("kez_echo_slash", 0), ("kez_grappling_claw", 0), ("kez_kazurai_katana", 0),
              ("kez_switch_weapons", 0), ("kez_raptor_dance", 0)]
KEZ_SAI = [("kez_falcon_rush", 0), ("kez_talon_toss", 0), ("kez_shodo_sai", 0),
           ("kez_switch_weapons", 0), ("kez_ravens_veil", 0)]


def test_kez_stance_switch_does_not_fire_hidden_abilities():
    # Switching stance renames four slots at once; none of those are casts.
    frames = [_slots_snap(*KEZ_KATANA), _slots_snap(*KEZ_SAI), _slots_snap(*KEZ_KATANA)]
    counts = _ability_starts(["kez_raptor_dance", "kez_ravens_veil", "kez_echo_slash", "kez_falcon_rush"], frames)
    assert not any(counts.values())


def test_kez_cast_in_stance_fires_once():
    cast = [("kez_echo_slash", 0), ("kez_grappling_claw", 0), ("kez_kazurai_katana", 6),
            ("kez_switch_weapons", 0), ("kez_raptor_dance", 0)]
    frames = [_slots_snap(*KEZ_KATANA), _slots_snap(*cast), _slots_snap(*KEZ_SAI)]
    counts = _ability_starts(["kez_kazurai_katana", "kez_raptor_dance"], frames)
    assert counts == {"kez_kazurai_katana": 1, "kez_raptor_dance": 0}


def test_in_place_transform_fires_once_and_the_revert_does_not():
    ready = [("centaur_work_horse", 0), ("centaur_stomp", 0)]
    mounted = [("centaur_mount", 0), ("centaur_stomp", 0)]
    cooling = [("centaur_work_horse", 20), ("centaur_stomp", 0)]
    frames = [_slots_snap(*ready), _slots_snap(*mounted), _slots_snap(*mounted),
              _slots_snap(*cooling), _slots_snap(*cooling)]
    assert _ability_starts(["centaur_work_horse"], frames) == {"centaur_work_horse": 1}


LARGO_NORMAL = [("largo_catchy_lick", 0), ("largo_frogstomp", 0), ("largo_croak_of_genius", 0),
                ("largo_amphibian_rhapsody", 0)]
LARGO_SONGS = [("largo_song_fight_song", 0), ("largo_song_double_time", 0),
               ("largo_song_good_vibrations", 0), ("largo_amphibian_rhapsody", 0)]


def test_largo_song_mode_switch_does_not_fire_hidden_abilities():
    # Amphibian Rhapsody renames three slots at once, and back again.
    frames = [_slots_snap(*LARGO_NORMAL), _slots_snap(*LARGO_SONGS), _slots_snap(*LARGO_NORMAL)]
    counts = _ability_starts(
        ["largo_catchy_lick", "largo_frogstomp", "largo_croak_of_genius",
         "largo_song_fight_song", "largo_song_double_time", "largo_song_good_vibrations"],
        frames,
    )
    assert not any(counts.values())


def test_largo_songs_share_a_cooldown_and_each_fires_once():
    on_cooldown = [(name, 1) for name, _ in LARGO_SONGS[:3]] + [LARGO_SONGS[3]]
    frames = [_slots_snap(*LARGO_NORMAL), _slots_snap(*LARGO_SONGS), _slots_snap(*on_cooldown),
              _slots_snap(*on_cooldown), _slots_snap(*LARGO_SONGS)]
    songs = [name for name, _ in LARGO_SONGS[:3]]
    assert _ability_starts(songs, frames) == dict.fromkeys(songs, 1)


def test_largo_rhapsody_fires_when_it_reverts_onto_cooldown():
    reverted = LARGO_NORMAL[:3] + [("largo_amphibian_rhapsody", 2)]
    frames = [_slots_snap(*LARGO_NORMAL), _slots_snap(*LARGO_SONGS), _slots_snap(*reverted)]
    assert _ability_starts(["largo_amphibian_rhapsody"], frames) == {"largo_amphibian_rhapsody": 1}
def _stun_rule(value=True):
    return {"id": "s", "monitor": {"type": "hero_bool", "field": "stunned", "value": value}, "actions": [_light(5)]}


def _flag_snap(stunned):
    return StateSnapshot(None, None, None, SimpleNamespace(stunned=stunned), None, None)


def test_hero_bool_is_active_from_the_change_until_it_changes_back():
    compiled, _, arbiter, _ = _setup([_stun_rule()])
    compiled.evaluate_all(_flag_snap(True))    # first look: only records
    compiled.evaluate_all(_flag_snap(False))
    compiled.evaluate_all(_flag_snap(True))    # becomes stunned
    compiled.evaluate_all(_flag_snap(False))   # ends
    assert arbiter.calls == [("set", 5, (1, 2, 3)), ("clear", 5)]


def test_hero_bool_rejects_unknown_and_alive_fields():
    for bad in ("alive", "health", "nope"):
        rule = {"id": "s", "monitor": {"type": "hero_bool", "field": bad}, "actions": [_light(5)]}
        try:
            RulesConfig.model_validate({"rules": [rule]})
        except ValueError:
            continue
        raise AssertionError(f"{bad} was accepted")


def test_hero_bool_event_is_serialized_for_the_editor():
    rule = {"id": "s", "monitor": {"type": "hero_bool", "field": "aghanims_shard", "value": True}, "actions": [_light(5)]}
    dumped = RulesConfig.model_validate({"rules": [rule]}).model_dump(mode="json")["rules"][0]["monitor"]
    assert dumped["event"] == "AGHANIMS_SHARD_TRUE"
    # the editor sends `event` back along with field/value; it is accepted and recomputed
    RulesConfig.model_validate({"rules": [{**rule, "monitor": dumped}]})
