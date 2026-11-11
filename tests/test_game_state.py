from src.rules import RulesConfig, compile_rules
from src.rules.actions import LightExecutor, SoundExecutor, WebhookExecutor
from src.rules.bus import EventBus
from src.rules.config import ActionType
from src.state.store import GameState


class FakeArbiter:
    def __init__(self):
        self.calls = []

    def set(self, priority, rgb):
        self.calls.append(priority)

    def clear(self, priority):
        pass

    def clear_all(self):
        pass

    def commit(self):
        pass


def _light(priority):
    return {"type": "light", "r": 1, "g": 2, "b": 3, "priority": priority}


def _state(rules):
    arbiter = FakeArbiter()
    executors = {
        ActionType.LIGHT: LightExecutor(arbiter),
        ActionType.PLAY_SOUND: SoundExecutor(sound=None),
        ActionType.WEBHOOK: WebhookExecutor(),
    }
    bus = EventBus()
    config = RulesConfig.model_validate({"rules": rules})
    return GameState(compile_rules(config.rules, bus, executors), bus, arbiter), arbiter


def _update(state, game_state, clock, matchid="1", **extra):
    state.update({"map": {
        "name": "start", "matchid": matchid, "game_time": clock + 90, "clock_time": clock, "daytime": True,
        "nightstalker_night": False, "game_state": f"DOTA_GAMERULES_STATE_{game_state}", "paused": False,
        "win_team": "none", "radiant_score": 0, "dire_score": 0, "customgamename": "", "ward_purchase_cooldown": 0,
    }, **extra})


def test_once_fires_before_the_horn():
    state, arbiter = _state([{"id": "o", "monitor": {"type": "once", "time": -10}, "actions": [_light(1)]}])
    for clock in (-12, -11, -10, -9):
        _update(state, "PRE_GAME", clock)
    assert arbiter.calls == [1]


def test_once_at_the_horn_fires_on_the_switch_to_in_progress():
    state, arbiter = _state([{"id": "o", "monitor": {"type": "once", "time": 0}, "actions": [_light(1)]}])
    _update(state, "PRE_GAME", -1)
    _update(state, "GAME_IN_PROGRESS", 0)
    _update(state, "GAME_IN_PROGRESS", 1)
    assert arbiter.calls == [1]


def test_periodic_with_no_start_fires_before_the_horn_and_a_start_time_still_holds():
    state, arbiter = _state([
        {"id": "any", "monitor": {"type": "periodic", "period": 60, "offset": -10}, "actions": [_light(1)]},
        {"id": "from0", "monitor": {"type": "periodic", "period": 60, "offset": -10, "min_time": 0}, "actions": [_light(2)]},
    ])
    for clock in (-11, -10, -9):
        _update(state, "PRE_GAME", clock)
    assert arbiter.calls == [1]


def test_clock_before_pre_game_is_ignored():
    state, arbiter = _state([{"id": "o", "monitor": {"type": "once", "time": -10}, "actions": [_light(1)]}])
    for game_state, clock in (("HERO_SELECTION", -25), ("STRATEGY_TIME", -29), ("TEAM_SHOWCASE", -15), ("TEAM_SHOWCASE", -5)):
        _update(state, game_state, clock)
    assert arbiter.calls == []


def test_hero_rules_wait_for_the_horn():
    state, arbiter = _state([{"id": "h", "monitor": {"type": "hero", "event": "HERO_KILLED"}, "actions": [_light(1)]}])
    hero = {"id": 1, "name": "npc_dota_hero_muerta", "alive": True}
    _update(state, "PRE_GAME", -20, hero=hero)
    _update(state, "PRE_GAME", -19, hero={**hero, "alive": False})
    assert arbiter.calls == []


def test_a_new_match_in_pre_game_resets_timers():
    state, arbiter = _state([{"id": "o", "monitor": {"type": "once", "time": -10}, "actions": [_light(1)]}])
    _update(state, "PRE_GAME", -11, matchid="1")
    _update(state, "PRE_GAME", -10, matchid="1")
    _update(state, "PRE_GAME", -11, matchid="2")
    _update(state, "PRE_GAME", -10, matchid="2")
    assert arbiter.calls == [1, 1]


def test_events_processor_resets_on_match_change():
    state, _ = _state([])
    chat = {"events": [{"game_time": 5, "event_type": "chat_message", "player_id": 1, "channel_type": 11, "message": "hi"}]}
    _update(state, "HERO_SELECTION", 0, matchid="1", **chat)
    _update(state, "HERO_SELECTION", 0, matchid="1", **chat)
    assert state._bus.published == 1
    _update(state, "HERO_SELECTION", 0, matchid="2", **chat)
    assert state._bus.published == 2
