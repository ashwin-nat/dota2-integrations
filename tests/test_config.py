import pytest
from pydantic import ValidationError

from src.rules.config import Rule, RulesConfig, drop_sound


def _rule(rule_id, event="COOLDOWN_READY", target="item_bkb"):
    return {
        "id": rule_id,
        "monitor": {"type": "item", "target": target, "event": event},
        "actions": [{"type": "light", "r": 1, "g": 2, "b": 3, "priority": hash(rule_id) % 1000 + 1}],
    }


def test_duplicate_rule_id_rejected():
    with pytest.raises(ValidationError, match="'a'"):
        RulesConfig.model_validate({"rules": [_rule("a"), _rule("a", target="item_blink")]})


def test_same_trigger_in_two_rules_is_accepted():
    # Each rule gets its own monitor and bus key, so this is fine
    RulesConfig.model_validate({"rules": [_rule("a"), _rule("b")]})


def test_distinct_rules_accepted():
    RulesConfig.model_validate({"rules": [_rule("a"), _rule("b", event="ITEM_LOST")]})


def test_map_rule_must_not_have_light_priority():
    rule = {
        "id": "day",
        "monitor": {"type": "map", "event": "DAYTIME_STARTED"},
        "actions": [{"type": "light", "r": 1, "g": 2, "b": 3, "priority": 4}],
    }
    with pytest.raises(ValidationError, match="priority cannot be set on map monitors"):
        RulesConfig.model_validate({"rules": [rule]})


def test_non_map_rule_requires_light_priority():
    rule = {
        "id": "bkb",
        "monitor": {"type": "item", "target": "item_bkb", "event": "COOLDOWN_READY"},
        "actions": [{"type": "light", "r": 1, "g": 2, "b": 3}],
    }
    with pytest.raises(ValidationError, match="requires a priority"):
        RulesConfig.model_validate({"rules": [rule]})


def test_unknown_monitor_type_rejected():
    rule = {"id": "x", "monitor": {"type": "nope", "event": "E"}, "actions": []}
    with pytest.raises(ValidationError, match="monitor"):
        RulesConfig.model_validate({"rules": [rule]})


def test_drop_sound_gives_its_odds_to_the_first_remaining_clip():
    action = {"type": "play_sound", "clips": [
        {"file": "a.mp3", "probability": 50}, {"file": "b.mp3", "probability": 30}, {"file": "c.mp3", "probability": 20},
    ]}
    assert drop_sound(action, "a.mp3") is True
    assert action["clips"] == [{"file": "b.mp3", "probability": 80}, {"file": "c.mp3", "probability": 20}]


def test_drop_sound_reports_when_no_clips_remain():
    action = {"type": "play_sound", "clips": [{"file": "a.mp3", "probability": 100}]}
    assert drop_sound(action, "a.mp3") is False


def _with_actions(*actions):
    return {"rules": [{"id": "r", "monitor": {"type": "hero", "event": "HERO_KILLED"}, "actions": list(actions)}]}


def _hook(url="http://localhost/x"):
    return {"type": "webhook", "endpoints": [{"url": url}]}


def test_two_actions_of_one_type_rejected():
    clip = {"type": "play_sound", "clips": [{"file": "x.mp3", "probability": 100}]}
    with pytest.raises(ValidationError, match="more than one play_sound"):
        Rule.model_validate(_with_actions(clip, clip)["rules"][0])
    with pytest.raises(ValidationError, match="more than one webhook"):
        Rule.model_validate(_with_actions(_hook(), _hook("http://localhost/y"))["rules"][0])


def test_one_action_of_each_type_accepted():
    light = {"type": "light", "r": 1, "g": 2, "b": 3, "priority": 1}
    RulesConfig.model_validate(_with_actions(light, _hook()))


def test_webhook_several_endpoints_validated_each():
    ok = {"url": "http://localhost/a"}
    RulesConfig.model_validate(_with_actions({"type": "webhook", "endpoints": [ok, {"url": "http://localhost/b"}]}))
    with pytest.raises(ValidationError, match="auth_type"):
        RulesConfig.model_validate(_with_actions({"type": "webhook", "endpoints": [ok, {"url": "http://h/b", "api_key": "k"}]}))
    with pytest.raises(ValidationError):
        RulesConfig.model_validate(_with_actions({"type": "webhook", "endpoints": []}))
