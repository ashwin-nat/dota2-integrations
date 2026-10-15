from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from src.lighting.arbiter import MAP_PRIORITY, LightingArbiter
from src.rules.config import ActionType, AnyAction, LightAction, MonitorType

logger = logging.getLogger(__name__)


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
    Lighting actions bypass the queues: they update the LightingArbiter
    synchronously and are applied when the arbiter commits at the end of the
    state update.
    """

    # The independent action queues
    QUEUE_KEYS = (ActionType.PLAY_SOUND, ActionType.WEBHOOK)

    def __init__(self, arbiter: LightingArbiter) -> None:
        self._arbiter = arbiter
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
            params = action.model_dump(exclude={"type", "enabled", "api_key"})
            logger.info(f"Rule {ctx.rule_id!r} fired {ctx.event_name}: {action.type} {params}")
            if isinstance(action, LightAction):
                # Map rules have no priority (config-enforced) and sit at the baseline.
                self._arbiter.set(action.priority or MAP_PRIORITY, (action.r, action.g, action.b))
            else:
                self._queues[action.type].put_nowait(QueuedAction(action=action, ctx=ctx))

    def retract(self, event_key: str) -> None:
        """Withdraw the light requests set by this event's rules (the state they signalled has ended)."""
        for action in self._listeners.get(event_key, []):
            if isinstance(action, LightAction) and action.enabled and action.priority is not None:
                self._arbiter.clear(action.priority)

    def queue_for(self, key: ActionType) -> asyncio.Queue[QueuedAction]:
        return self._queues[key]
