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
    return {"type": "webhook", "endpoints": [{"url": "http://localhost/x"}], "enabled": enabled}


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
        {"id": "w", "monitor": {"type": "item", "target": "item_ward_sentry", "event": "COOLDOWN_STARTED"}, "actions": [_light(11)]},
        {"id": "m", "monitor": {"type": "midas", "event": "CHARGED"}, "actions": [_light(4)]},
        {"id": "mo", "monitor": {"type": "midas", "event": "OVERCHARGED"}, "actions": [_light(5)]},
        {"id": "b", "monitor": {"type": "blink", "event": "COOLDOWN_STARTED"}, "actions": [_light(6)]},
        {"id": "h", "monitor": {"type": "hero", "event": "HERO_KILLED"}, "actions": [_light(7)]},
        {"id": "a", "monitor": {"type": "ability", "target": "x", "event": "COOLDOWN_STARTED"}, "actions": [_light(8)]},
        {"id": "p", "monitor": {"type": "periodic", "period": 30}, "actions": [_light(9)]},
        {"id": "hi", "monitor": {"type": "hero_int", "field": "buyback_cooldown"}, "actions": [_light(10)]},
        {"id": "hb", "monitor": {"type": "hero_buff", "buff": "modifier_x", "event": "STACK_LOST"}, "actions": [_light(12)]},
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
    # Rules built in code skip RulesConfig's duplicate-id check
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


def test_charge_of_darkness_fires_once_on_cast_not_on_arrival():
    # recordings/charge_trigger_twice_bug.jsonl: the cast reads 22, the arrival restarts the
    # running cooldown (16 -> 22). That rise is not a cast. Short charge: 22 -> 22, no rise.
    from src.state.abilities import Abilities, Ability

    def frame(cooldown):
        a = Ability("ability0", "spirit_breaker_charge_of_darkness", 1, cooldown == 0, False, True,
                    cooldown, 23, False)
        return StateSnapshot(None, None, Abilities({"ability0": a}), None, None, None)

    target = ["spirit_breaker_charge_of_darkness"]
    long = [0, 22, 21, 20, 19, 18, 16, 22, 21, 20, 0, 22]
    assert _ability_starts(target, [frame(c) for c in long]) == {target[0]: 2}
    short = [0, 22, 22, 21, 19]
    assert _ability_starts(target, [frame(c) for c in short]) == {target[0]: 1}


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


def _buyback_rule():
    return {"id": "bb", "monitor": {"type": "hero_int", "field": "buyback_cooldown"}, "actions": [_light(5)]}


def _bb_snap(cooldown):
    return StateSnapshot(None, None, None, SimpleNamespace(buyback_cooldown=cooldown), None, None)


def test_hero_int_buyback_fires_once_on_the_rise_and_ends_next_frame():
    # Real Huskar and Vishnu games: buyback_cooldown went 0 -> 3066 / 3079 (a game-time stamp, not a
    # countdown) in the frame the buyback was bought, and then stayed at that value.
    compiled, _, arbiter, _ = _setup([_buyback_rule()])
    for cooldown in (0, 0, 0, 3066, 3066, 3066):
        compiled.evaluate_all(_bb_snap(cooldown))
    assert arbiter.calls == [("set", 5, (1, 2, 3)), ("clear", 5)]


def test_hero_int_does_not_fire_on_first_frame_or_when_value_falls():
    compiled, _, arbiter, _ = _setup([_buyback_rule()])
    compiled.evaluate_all(_bb_snap(3066))   # joined with the buyback already used: only records
    compiled.evaluate_all(_bb_snap(3066))
    compiled.evaluate_all(_bb_snap(0))      # cooldown over
    assert arbiter.calls == []


def test_hero_int_ignores_missing_hero_and_missing_field_without_losing_its_place():
    compiled, _, arbiter, _ = _setup([_buyback_rule()])
    compiled.evaluate_all(_bb_snap(0))
    compiled.evaluate_all(_bb_snap(None))
    compiled.evaluate_all(StateSnapshot(None, None, None, None, None, None))
    compiled.evaluate_all(_bb_snap(3066))
    assert arbiter.calls == [("set", 5, (1, 2, 3))]


def test_hero_int_clear_resets_the_previous_value():
    compiled, _, arbiter, _ = _setup([_buyback_rule()])
    compiled.evaluate_all(_bb_snap(0))
    compiled.clear_all()
    compiled.evaluate_all(_bb_snap(3066))   # first frame of a new match: records only
    assert arbiter.calls == []


def test_hero_int_rejects_non_number_fields_and_serializes_its_event():
    for bad in ("stunned", "name", "nope"):
        rule = {"id": "s", "monitor": {"type": "hero_int", "field": bad}, "actions": [_light(5)]}
        try:
            RulesConfig.model_validate({"rules": [rule]})
        except ValueError:
            continue
        raise AssertionError(f"{bad} was accepted")
    dumped = RulesConfig.model_validate({"rules": [_buyback_rule()]}).model_dump(mode="json")["rules"][0]["monitor"]
    assert dumped["event"] == "BUYBACK_COOLDOWN_RISES"
    RulesConfig.model_validate({"rules": [{**_buyback_rule(), "monitor": dumped}]})


def _buff_rule(buff, event="STACK_GAINED"):
    return {"id": "hb", "monitor": {"type": "hero_buff", "buff": buff, "event": event}, "actions": [_light(5)]}


def _buff_snap(buffs):
    return StateSnapshot(None, None, None, SimpleNamespace(permanent_buffs=buffs), None, None)


def _buff_calls(rule, frames):
    compiled, _, arbiter, _ = _setup([rule])
    for buffs in frames:
        compiled.evaluate_all(_buff_snap(buffs))
    return arbiter.calls


_TIDE = "modifier_tidehunter_leviathans_catch_counter"
_MUERTA = "modifier_muerta_supernatural"


def test_hero_buff_tidehunter_fires_on_each_new_stack_and_not_on_the_reset():
    # vishnu_test: {} -> 1 at 1837 s, 1 -> 2 at 2069 s, then {} again at the next match
    # (the key vanishes, so a drop to 0), then 1 again in that match.
    frames = [{}, {}, {_TIDE: 1}, {_TIDE: 1}, {_TIDE: 2}, {_TIDE: 2}, {}, {_TIDE: 1}]
    calls = _buff_calls(_buff_rule(_TIDE), frames)
    assert calls == [("set", 5, (1, 2, 3)), ("clear", 5)] * 2 + [("set", 5, (1, 2, 3))]  # last one still active


def test_hero_buff_muerta_gained_and_lost_are_separate_rules():
    # muerta recording: 0 -> 1 -> 2 -> 1 (665 s) ... 4 -> 2 (1206 s) ... 4 -> 6 (1763 s)
    frames = [{_MUERTA: 0}, {_MUERTA: 1}, {_MUERTA: 2}, {_MUERTA: 1}, {_MUERTA: 4}, {_MUERTA: 2}, {_MUERTA: 6}]
    gained = _buff_calls(_buff_rule(_MUERTA), frames)
    lost = _buff_calls(_buff_rule(_MUERTA, "STACK_LOST"), frames)
    assert [c for c in gained if c[0] == "set"] == [("set", 5, (1, 2, 3))] * 4   # 0>1, 1>2, 1>4, 2>6
    assert [c for c in lost if c[0] == "set"] == [("set", 5, (1, 2, 3))] * 2     # 2>1, 4>2


def test_hero_buff_first_frame_missing_hero_and_other_buffs_do_not_fire():
    rule = _buff_rule(_MUERTA)
    assert _buff_calls(rule, [{_MUERTA: 15}, {_MUERTA: 15}]) == []        # joined mid-match
    assert _buff_calls(rule, [{}, {_TIDE: 3}]) == []                      # a different buff
    compiled, _, arbiter, _ = _setup([rule])
    compiled.evaluate_all(_buff_snap({_MUERTA: 1}))
    compiled.evaluate_all(StateSnapshot(None, None, None, None, None, None))
    compiled.evaluate_all(_buff_snap({_MUERTA: 2}))                       # place kept across the gap
    assert arbiter.calls == [("set", 5, (1, 2, 3))]


def test_hero_buff_clear_resets_the_previous_count():
    compiled, _, arbiter, _ = _setup([_buff_rule(_MUERTA)])
    compiled.evaluate_all(_buff_snap({_MUERTA: 1}))
    compiled.clear_all()
    compiled.evaluate_all(_buff_snap({_MUERTA: 5}))   # first frame of a new match: records only
    assert arbiter.calls == []


def test_hero_buff_config_round_trips_and_needs_a_buff():
    good = _buff_rule(_MUERTA, "STACK_LOST")
    dumped = RulesConfig.model_validate({"rules": [good]}).model_dump(mode="json")["rules"][0]["monitor"]
    assert dumped == good["monitor"]
    bad = {**good, "monitor": {"type": "hero_buff", "event": "STACK_LOST"}}
    try:
        RulesConfig.model_validate({"rules": [bad]})
    except ValueError:
        return
    raise AssertionError("a hero_buff rule without a buff was accepted")


# Real ward frames (enemy_torm_ad t=1113-1121, ad_snap_buyback t=446-450, soundbo.log 2026-11-22):
# a use shows cooldown 1 / max_cooldown 1 for a frame or two, then max_cooldown stays 1 at
# cooldown 0 for as long as the ward is held. The generic item monitor read that as a cast on
# every frame.
def _ward_snap(name, cooldown, max_cooldown, charges=1, present=True):
    from src.state.items import SingleChargeItem
    item = SingleChargeItem(
        slot_id="slot0", name=name, purchaser=0, item_level=1, can_cast=cooldown == 0,
        cooldown=cooldown, max_cooldown=max_cooldown, passive=False, item_charges=charges, charges=charges,
    )
    items = SimpleNamespace(find=lambda n: item if present and n == name else None)
    return StateSnapshot(items, None, None, None, None, None)


def _ward_starts(name, frames):
    compiled, _, arbiter, _ = _setup([
        {"id": "w", "monitor": {"type": "item", "target": name, "event": "COOLDOWN_STARTED"}, "actions": [_light(1)]},
    ])
    for frame in frames:
        compiled.evaluate_all(frame)
    return sum(1 for call in arbiter.calls if call[0] == "set")


def test_ward_fires_once_on_use_and_not_every_frame_after():
    for name in ("item_ward_observer", "item_ward_sentry", "item_ward_dispenser"):
        frames = [_ward_snap(name, 0, 0, 2)] * 3 + [
            _ward_snap(name, 1, 1, 1),   # placed
            _ward_snap(name, 0, 1, 1),   # max_cooldown stays 1 from here on
        ] + [_ward_snap(name, 0, 1, 1)] * 10
        assert _ward_starts(name, frames) == 1, name


def test_ward_stuck_max_cooldown_alone_never_fires():
    # Joined mid-match holding a ward in the 0 / 1 state (the 2026-11-22 loop)
    assert _ward_starts("item_ward_observer", [_ward_snap("item_ward_observer", 0, 1)] * 20) == 0


def test_last_charge_ward_fires_once_even_though_charges_do_not_drop():
    name = "item_ward_observer"
    frames = [_ward_snap(name, 0, 0)] * 2 + [_ward_snap(name, 1, 1)] * 2 + [
        _ward_snap(name, 0, 0), _ward_snap(name, 0, 0, present=False)]
    assert _ward_starts(name, frames) == 1


def test_ward_fires_again_for_the_next_use():
    name = "item_ward_observer"
    frames = [_ward_snap(name, 0, 0, 2), _ward_snap(name, 1, 1, 1), _ward_snap(name, 0, 1, 1),
              _ward_snap(name, 1, 1, 0), _ward_snap(name, 0, 1, 0)]
    assert _ward_starts(name, frames) == 2


def test_parse_hero_reads_permanent_buffs_stack_counts():
    from src.state.hero import parse_hero
    base = {"facet": 1, "id": 1, "name": "npc_dota_hero_muerta"}
    assert parse_hero(base).permanent_buffs == {}
    raw = {**base, "permanent_buffs": {_MUERTA: {"stack_count": 3}, "modifier_item_aghanims_shard": {"stack_count": 0}}}
    assert parse_hero(raw).permanent_buffs == {_MUERTA: 3, "modifier_item_aghanims_shard": 0}
