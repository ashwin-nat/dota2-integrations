from __future__ import annotations

from dataclasses import dataclass, field

from src.rules.bus import RuleEventBus
from src.rules.config import AnyAction, ItemMonitorConfig, MidasMonitorConfig, MapMonitorConfig, HeroMonitorConfig, ResetLightAction, Rule
from src.rules.item_monitors import ITEM_MONITOR_REGISTRY, MIDAS_MONITOR_REGISTRY, ItemMonitor
from src.rules.map_monitor import MapMonitor
from src.rules.hero_monitor import HeroMonitor


@dataclass
class CompiledRules:
    item_monitors: list[ItemMonitor] = field(default_factory=list)
    map_monitors: list[MapMonitor] = field(default_factory=list)
    hero_monitors: list[HeroMonitor] = field(default_factory=list)


def _enabled(actions: list[AnyAction]) -> list[AnyAction]:
    return [a for a in actions if a.enabled]


def compile_rules(rules: list[Rule], bus: RuleEventBus) -> CompiledRules:
    compiled = CompiledRules()

    for rule in rules:
        m = rule.monitor
        actions = _enabled(rule.actions)

        if isinstance(m, ItemMonitorConfig):
            if actions:
                bus.register(m.event_key, actions)
                cls = ITEM_MONITOR_REGISTRY[m.event]
                compiled.item_monitors.append(cls(m.target, m.event_key, bus))

        elif isinstance(m, MidasMonitorConfig):
            if actions:
                bus.register(m.event_key, actions)
                cls = MIDAS_MONITOR_REGISTRY[m.event]
                compiled.item_monitors.append(cls("item_hand_of_midas", m.event_key, bus))

        elif isinstance(m, MapMonitorConfig):
            for action in actions:
                if isinstance(action, ResetLightAction):
                    raise ValueError(
                        f"Rule {rule.id!r}: reset_light cannot be used on map monitors"
                    )
            if actions:
                bus.register(m.event_key, actions)
                compiled.map_monitors.append(MapMonitor(m.event, m.event_key, bus))

        elif isinstance(m, HeroMonitorConfig):
            if actions:
                bus.register(m.event_key, actions)
                compiled.hero_monitors.append(HeroMonitor(m.event, m.event_key, bus))

        else:
            raise ValueError(f"Unknown monitor type: {m.type!r}")

    return compiled
