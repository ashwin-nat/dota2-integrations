from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
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
    # Stamped by RuleEventBus.emit from the game state at fire time
    game_time: int | None = None
    clock_time: int | None = None

    def __str__(self) -> str:
        return (
            f"rule={self.rule_id!r} monitor={self.monitor_type} event={self.event_name} "
            f"game_time={self.game_time} clock_time={self.clock_time} data={self.data}"
        )


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
        self._game_time: int | None = None
        self._clock_time: int | None = None

    def set_time(self, game_time: int, clock_time: int) -> None:
        """Called by GameState on each update, before monitors run."""
        self._game_time = game_time
        self._clock_time = clock_time

    def register(self, event_key: str, actions: list[AnyAction], context: EventContext) -> None:
        """Called at compile time only — never at runtime."""
        self._listeners.setdefault(event_key, []).extend(actions)
        self._contexts[event_key] = context

    def reset(self) -> None:
        """Drop every registered listener, before recompiling rules on a config reload."""
        self._listeners.clear()
        self._contexts.clear()

    def emit(self, event_key: str) -> None:
        """Non-blocking: fan out each enabled action to its type queue."""
        actions = self._listeners.get(event_key, [])
        ctx = self._contexts.get(event_key)
        if not actions or ctx is None:
            return
        ctx = replace(ctx, game_time=self._game_time, clock_time=self._clock_time)
        for action in actions:
            if not action.enabled:
                continue
            if isinstance(action, LightAction):
                # Lights never reach ActionExecutor, so log them here
                logger.info(f"{ctx} -> light ({action.r}, {action.g}, {action.b}) priority={action.priority}")
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
