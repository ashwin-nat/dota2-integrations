from types import SimpleNamespace

from src.rules.actions import ActionBinding, SoundExecutor
from src.rules.bus import Event, EventType
from src.rules.config import ActionType
from src.rules.monitor_config import MonitorType
from tests.test_game_state import _state, _update


def _capture(state):
    """Collect every STARTED event published on the state's bus."""
    events = []
    state._bus.subscribe("m", events.append)
    return events


def test_first_update_events_are_initial_and_later_ones_are_not():
    state, _ = _state([{"id": "m", "monitor": {"type": "map", "event": "DAYTIME_STARTED"}, "actions": [{"type": "light", "r": 1, "g": 2, "b": 3}]}])
    events = _capture(state)
    _update(state, "GAME_IN_PROGRESS", 10)  # first look: day already true
    assert [e.initial for e in events] == [True]
    # night, then day again: a real change
    state.update({"map": {**state.raw["map"], "daytime": False}})
    state.update({"map": {**state.raw["map"], "daytime": True}})
    assert [e.initial for e in events] == [True, False]


def test_a_match_change_makes_the_next_first_look_initial_again():
    state, _ = _state([{"id": "m", "monitor": {"type": "map", "event": "DAYTIME_STARTED"}, "actions": [{"type": "light", "r": 1, "g": 2, "b": 3}]}])
    events = _capture(state)
    _update(state, "GAME_IN_PROGRESS", 10, matchid="1")
    _update(state, "GAME_IN_PROGRESS", 10, matchid="2")
    assert [e.initial for e in events] == [True, True]


def test_the_initial_flag_does_not_leak_to_events_outside_a_first_update():
    state, _ = _state([{"id": "m", "monitor": {"type": "map", "event": "DAYTIME_STARTED"}, "actions": [{"type": "light", "r": 1, "g": 2, "b": 3}]}])
    _update(state, "GAME_IN_PROGRESS", 10)
    assert state._bus.initial is False


def test_sound_executor_skips_initial_events_only():
    executor = SoundExecutor(sound=None)
    executor.register("r", ActionBinding("r", MonitorType.MAP, "DAYTIME_STARTED", SimpleNamespace(type=ActionType.PLAY_SOUND)))
    executor.on_event(Event("r", EventType.STARTED, 0, 0, initial=True))
    assert executor._queue.qsize() == 0
    executor.on_event(Event("r", EventType.STARTED, 0, 0))
    assert executor._queue.qsize() == 1


def _blink(present):
    blink = {"name": "item_blink", "purchaser": 0, "item_level": 1, "can_cast": True,
             "cooldown": 0, "max_cooldown": 0, "passive": False}
    return {"slot0": blink if present else {"name": "empty"}}


def test_item_already_owned_on_first_look_is_initial_but_a_later_purchase_is_not():
    rule = {"id": "m", "monitor": {"type": "blink", "event": "ITEM_ACQUIRED"},
            "actions": [{"type": "light", "r": 1, "g": 2, "b": 3, "priority": 1}]}

    # Joined mid-game already holding Blink: the first look reports it, no sound
    state, _ = _state([rule])
    events = _capture(state)
    _update(state, "GAME_IN_PROGRESS", 10, items=_blink(True))
    _update(state, "GAME_IN_PROGRESS", 11, items=_blink(True))
    assert [e.initial for e in events] == [True]

    # Bought it later: a real event
    state, _ = _state([rule])
    events = _capture(state)
    _update(state, "GAME_IN_PROGRESS", 10, items=_blink(False))
    _update(state, "GAME_IN_PROGRESS", 11, items=_blink(True))
    assert [e.initial for e in events] == [False]
