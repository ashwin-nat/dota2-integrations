from __future__ import annotations

from dataclasses import dataclass, field

from src.rules.bus import RuleEventBus
from src.rules.config import ItemMonitorConfig, MidasMonitorConfig, MapMonitorConfig, Rule
from src.rules.item_monitors import ITEM_MONITOR_REGISTRY, MIDAS_MONITOR_REGISTRY, ItemMonitor
from src.rules.map_monitor import MapMonitor


@dataclass
class CompiledRules:
    item_monitors: list[ItemMonitor] = field(default_factory=list)
    map_monitors: list[MapMonitor] = field(default_factory=list)


def compile_rules(rules: list[Rule], bus: RuleEventBus) -> CompiledRules:
    compiled = CompiledRules()

    for rule in rules:
        m = rule.monitor

        if isinstance(m, ItemMonitorConfig):
            bus.register(m.event_key, rule.actions)
            cls = ITEM_MONITOR_REGISTRY[m.event]
            compiled.item_monitors.append(cls(m.target, m.event_key, bus))

        elif isinstance(m, MidasMonitorConfig):
            bus.register(m.event_key, rule.actions)
            cls = MIDAS_MONITOR_REGISTRY[m.event]
            compiled.item_monitors.append(cls("item_hand_of_midas", m.event_key, bus))

        elif isinstance(m, MapMonitorConfig):
            bus.register(m.event_key, rule.actions)
            compiled.map_monitors.append(MapMonitor(m.event, m.event_key, bus))

        else:
            raise ValueError(f"Unknown monitor type: {m.type!r}")

    return compiled
