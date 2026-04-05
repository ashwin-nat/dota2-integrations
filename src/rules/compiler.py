from __future__ import annotations

from dataclasses import dataclass, field

from src.rules.bus import RuleEventBus
from src.rules.config import ItemMonitorConfig, MapMonitorConfig, Rule
from src.rules.item_monitors import ITEM_MONITOR_REGISTRY, ItemMonitor


@dataclass
class CompiledRules:
    # maps item name → list of monitors to evaluate for that item
    monitors_by_item: dict[str, list[ItemMonitor]] = field(default_factory=dict)
    # maps event key → (no per-item indexing needed for global monitors)
    global_event_keys: list[str] = field(default_factory=list)


def compile_rules(rules: list[Rule], bus: RuleEventBus) -> CompiledRules:
    compiled = CompiledRules()

    for rule in rules:
        m = rule.monitor

        if isinstance(m, ItemMonitorConfig):
            bus.register(m.event_key, rule.actions)
            cls = ITEM_MONITOR_REGISTRY[m.event]
            compiled.monitors_by_item.setdefault(m.target, []).append(cls(m.event_key, bus))

        elif isinstance(m, MapMonitorConfig):
            bus.register(m.event_key, rule.actions)
            compiled.global_event_keys.append(m.event_key)

        else:
            raise ValueError(f"Unknown monitor type: {m.type!r}")

    return compiled
