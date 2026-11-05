from __future__ import annotations

import logging

from src.lighting.arbiter import MAP_PRIORITY, LightingArbiter
from src.rules.actions.base import ActionExecutor, describe
from src.rules.bus import Event, EventType
from src.rules.config import ActionType, LightAction

logger = logging.getLogger(__name__)


class LightExecutor(ActionExecutor[LightAction]):
    """Sets and clears light requests on the arbiter synchronously; the arbiter commits once per update."""

    action_type = ActionType.LIGHT

    def __init__(self, arbiter: LightingArbiter) -> None:
        super().__init__()
        self._arbiter = arbiter

    def on_event(self, event: Event) -> None:
        """STARTED sets each bound light request; ENDED clears the ones that have a priority."""
        for binding in self._bindings.get(event.key, []):
            action = binding.action
            if event.type is EventType.STARTED:
                logger.info(
                    f"{describe(binding, event)} -> light ({action.r}, {action.g}, {action.b}) "
                    f"priority={action.priority}"
                )
                # Map rules have no priority (config-enforced) and sit at the baseline.
                self._arbiter.set(action.priority or MAP_PRIORITY, (action.r, action.g, action.b))
            elif action.priority is not None:
                self._arbiter.clear(action.priority)
