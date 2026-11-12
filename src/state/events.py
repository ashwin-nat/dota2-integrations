"""GSI `events` block: a rolling list repeated on every frame (each event lingers ~27 frames).

`EventProcessor` remembers the previous list and hands only the new entries onto the EventBus, parsed
into typed payloads under the key `event:<event_type>`. Event types without a parser are ignored.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

from src.rules.bus import EventBus, EventPayload

logger = logging.getLogger(__name__)


class ChatChannel(IntEnum):
    ALL = 11
    TEAM = 12


@dataclass(frozen=True)
class ChatMessage(EventPayload):
    game_time: int  # counts from match load, not the in-game clock
    player_id: int
    channel: ChatChannel | int
    message: str


def parse_chat_message(data: dict) -> ChatMessage:
    channel = data["channel_type"]
    try:
        channel = ChatChannel(channel)
    except ValueError:
        pass  # unknown channel, keep the number
    return ChatMessage(
        game_time=data["game_time"],
        player_id=data["player_id"],
        channel=channel,
        message=data["message"],
    )


PARSERS: dict[str, Callable[[dict], EventPayload]] = {
    "chat_message": parse_chat_message,
}



def event_key(event_type: str) -> str:
    """Bus key for a game event type. Rule keys are rule ids, so the prefix keeps them apart."""
    return f"event:{event_type}"


def _key(raw: dict) -> str:
    return json.dumps(raw, sort_keys=True)


class EventProcessor:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self.latest: list[dict] = []  # raw e    def reset(self, reason: str) -> None:

    def reset(self, reason: str = "") -> None:
        self.latest = []
        logger.info(f"EventProcessor reset: {reason}")

    def process(self, raw_events: list[dict]) -> None:
        """Store the frame's events; parse and emit the ones not in the previous frame."""
        seen = Counter(_key(e) for e in self.latest)
        self.latest = raw_events
        for raw in raw_events:
            key = _key(raw)
            if seen[key] > 0:  # already delivered (a repeat of the same text counts as new once the count grows)
                seen[key] -= 1
                continue
            event_type = raw.get("event_type")
            parser = PARSERS.get(event_type)
            if parser is None:
                continue
            try:
                payload = parser(raw)
            except Exception as e:
                logger.warning(f"Could not parse event {raw}: {e}")
                continue
            self._bus.emit(event_key(event_type), payload)
