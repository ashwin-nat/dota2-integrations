from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.rules.config import ActionType, AnyAction, MonitorType

# Action types that share the lighting queue
_LIGHT_TYPES = {ActionType.LIGHT, ActionType.RESET_LIGHT}

# Canonical queue key for each action type
def _queue_key(action_type: ActionType) -> ActionType:
    if action_type in _LIGHT_TYPES:
        return ActionType.LIGHT
    return action_type


@dataclass
class EventContext:
    """Metadata attached to a fired rule event, passed through to action executors."""
    rule_id: str
    monitor_type: MonitorType
    event_name: str
    data: dict[str, Any] = field(default_factory=dict)


# Items placed on per-type queues
@dataclass
class QueuedAction:
    action: AnyAction
    ctx: EventContext


class RuleEventBus:
    """Async event bus with one queue per action type.

    On emit, each action in the rule is routed to its type's queue.
    reset_light shares the light queue (same subsystem, must stay serial).
    """

    # The four independent action queues
    QUEUE_KEYS = (ActionType.PLAY_SOUND, ActionType.LIGHT, ActionType.LOGGER, ActionType.WEBHOOK)

    def __init__(self) -> None:
        self._listeners: dict[str, list[AnyAction]] = {}
        self._contexts: dict[str, EventContext] = {}
        self._queues: dict[ActionType, asyncio.Queue[QueuedAction]] = {
            key: asyncio.Queue() for key in self.QUEUE_KEYS
        }

    def register(self, event_key: str, actions: list[AnyAction], context: EventContext) -> None:
        """Called at compile time only — never at runtime."""
        self._listeners.setdefault(event_key, []).extend(actions)
        self._contexts[event_key] = context

    def emit(self, event_key: str) -> None:
        """Non-blocking: fan out each enabled action to its type queue."""
        actions = self._listeners.get(event_key, [])
        ctx = self._contexts.get(event_key)
        if not actions or ctx is None:
            return
        for action in actions:
            if not action.enabled:
                continue
            q = self._queues[_queue_key(action.type)]
            q.put_nowait(QueuedAction(action=action, ctx=ctx))

    def queue_for(self, key: ActionType) -> asyncio.Queue[QueuedAction]:
        return self._queues[key]
