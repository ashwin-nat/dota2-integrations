from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.rules.actions import ActionBinding, ActionExecutor
from src.rules.bus import EventBus
from src.rules.config import ActionType, Rule
from src.rules.monitor_base import Monitor, StateSnapshot

logger = logging.getLogger(__name__)


@dataclass
class CompiledRules:
    """Every monitor built from rules.json, one per rule, in rule order."""
    monitors: list[Monitor] = field(default_factory=list)

    def evaluate_all(self, snap: StateSnapshot) -> None:
        """Run every monitor against one update."""
        for monitor in self.monitors:
            monitor.evaluate(snap)

    def clear_all(self) -> None:
        """Reset every monitor's per-match state (on a match change)."""
        for monitor in self.monitors:
            monitor.clear()

    def counts(self) -> dict[str, int]:
        """Number of monitors per monitor type, for the startup log."""
        return dict(Counter(m.type.value for m in self.monitors))


def compile_rules(
    rules: list[Rule],
    bus: EventBus,
    executors: Mapping[ActionType, ActionExecutor[Any]],
) -> CompiledRules:
    """Build one monitor per rule, register its enabled actions on the executors, and subscribe them.

    Every rule publishes under its own key (its id), so each key has exactly one monitor and
    one list of actions. Rules on the same trigger just get separate monitors, and every action
    still runs once. `RulesConfig` rejects duplicate ids in rules.json, but followed friends'
    rules are added without that check, so a repeated id is skipped here with a warning
    (the first rule with the id wins).
    """
    compiled = CompiledRules()
    seen_ids: set[str] = set()

    for rule in rules:
        m = rule.monitor
        actions = [a for a in rule.actions if a.enabled]
        if not actions:
            continue
        if rule.id in seen_ids:
            logger.warning(f"Skipping rule {rule.id!r}: another rule already has this id")
            continue
        seen_ids.add(rule.id)
        monitor = m.build(bus, rule.id)
        compiled.monitors.append(monitor)
        for action in actions:
            executors[action.type].register(
                rule.id, ActionBinding(rule.id, m.type, m.event, action)
            )

    for executor in executors.values():
        for key in executor.keys():
            bus.subscribe(key, executor.on_event)

    return compiled
