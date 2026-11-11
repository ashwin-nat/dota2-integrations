import json
from pathlib import Path

from src.rules.bus import EventBus
from src.state.events import ChatChannel, ChatMessage, EventProcessor, event_key, subscribe_defaults


def _chat(t, text, player=3, channel=12):
    return {"game_time": t, "event_type": "chat_message", "player_id": player, "channel_type": channel, "message": text}


def _collect():
    bus = EventBus()
    proc = EventProcessor(bus)
    got = []
    bus.subscribe(event_key("chat_message"), lambda e: got.append(e.payload))
    return proc, got


def test_chat_is_parsed_once_while_it_lingers():
    proc, got = _collect()
    for _ in range(3):
        proc.process([_chat(110, "me pls")])
    assert got == [ChatMessage(110, 3, ChatChannel.TEAM, "me pls")]


def test_only_the_delta_is_emitted():
    proc, got = _collect()
    proc.process([_chat(110, "a")])
    proc.process([_chat(110, "a"), _chat(111, "b", channel=11)])
    assert [m.message for m in got] == ["a", "b"]
    assert got[1].channel is ChatChannel.ALL


def test_identical_message_repeated_is_new():
    proc, got = _collect()
    proc.process([_chat(110, "gg")])
    proc.process([_chat(110, "gg"), _chat(110, "gg")])
    assert len(got) == 2


def test_unparsed_and_malformed_events_are_ignored_but_stored():
    proc, got = _collect()
    raws = [{"event_type": "roshan_killed", "killer_player_id": 1}, {"event_type": "chat_message"}]
    proc.process(raws)
    assert got == [] and proc.latest == raws


def test_huskar_recording_yields_each_chat_once():
    path = Path(__file__).parent.parent / "recordings" / "huskar_ad_2026_11_08.jsonl"
    if not path.exists():
        return
    proc, got = _collect()
    for line in path.read_text(encoding="utf8").splitlines():
        proc.process(json.loads(line)["data"].get("events") or [])
    assert len(got) == 33


def test_processor_reset_redelivers_lingering_events():
    proc, got = _collect()
    proc.process([_chat(110, "a")])
    proc.reset()
    proc.process([_chat(110, "a")])
    assert len(got) == 2


def test_default_chat_subscriber_survives_bus_reset(caplog):
    bus = EventBus()
    subscribe_defaults(bus)
    bus.reset()
    with caplog.at_level("INFO"):
        EventProcessor(bus).process([_chat(1, "hello")])
    assert "Chat [team] player 3: hello" in caplog.text
