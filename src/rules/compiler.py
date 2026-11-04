from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.rules.bus import EventContext, RuleEventBus
from src.rules.ability_monitors import ABILITY_MONITOR_REGISTRY, AbilityMonitor
from src.rules.config import (
    AbilityMonitorConfig,
    AnyAction,
    AnyMonitor,
    BlinkMonitorConfig,
    HeroMonitorConfig,
    ItemMonitorConfig,
    MapMonitorConfig,
    MidasMonitorConfig,
    MonitorType,
    PeriodicMonitorConfig,
    Rule,
)
from src.rules.periodic_monitor import PeriodicMonitor
from src.rules.item_monitors import BLINK_MONITOR_REGISTRY, ITEM_MONITOR_REGISTRY, ITEM_SPECIFIC_REGISTRIES, MIDAS_MONITOR_REGISTRY, ItemMonitor
from src.rules.map_monitor import MapMonitor
from src.rules.hero_monitor import HeroMonitor


@dataclass
class CompiledRules:
    item_monitors: list[ItemMonitor] = field(default_factory=list)
    map_monitors: list[MapMonitor] = field(default_factory=list)
    hero_monitors: list[HeroMonitor] = field(default_factory=list)
    ability_monitors: list[AbilityMonitor] = field(default_factory=list)
    periodic_monitors: list[PeriodicMonitor] = field(default_factory=list)


def _enabled(actions: list[AnyAction]) -> list[AnyAction]:
    return [a for a in actions if a.enabled]


_MonitorHandler = Callable[[Rule, AnyMonitor, list[AnyAction], RuleEventBus, EventContext, CompiledRules], None]


def _compile_item(_: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, ItemMonitorConfig)
    bus.register(m.event_key, actions, ctx)
    registry = ITEM_SPECIFIC_REGISTRIES.get(m.target, ITEM_MONITOR_REGISTRY)
    compiled.item_monitors.append(registry[m.event](m.target, m.event_key, bus))


def _compile_midas(_: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, MidasMonitorConfig)
    bus.register(m.event_key, actions, ctx)
    compiled.item_monitors.append(MIDAS_MONITOR_REGISTRY[m.event]("item_hand_of_midas", m.event_key, bus))


def _compile_blink(_: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, BlinkMonitorConfig)
    bus.register(m.event_key, actions, ctx)
    compiled.item_monitors.append(BLINK_MONITOR_REGISTRY[m.event]("item_blink", m.event_key, bus))


def _compile_map(_: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, MapMonitorConfig)
    bus.register(m.event_key, actions, ctx)
    compiled.map_monitors.append(MapMonitor(m.event, m.event_key, bus))


def _compile_hero(_: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, HeroMonitorConfig)
    bus.register(m.event_key, actions, ctx)
    compiled.hero_monitors.append(HeroMonitor(m.event, m.event_key, bus))


def _compile_ability(_: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, AbilityMonitorConfig)
    bus.register(m.event_key, actions, ctx)
    compiled.ability_monitors.append(ABILITY_MONITOR_REGISTRY[m.event](m.target, m.event_key, bus))


def _compile_periodic(rule: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, PeriodicMonitorConfig)
    # Per rule, so two timers with the same schedule each fire their own actions once
    key = f"{m.event_key}{rule.id}__"
    bus.register(key, actions, ctx)
    compiled.periodic_monitors.append(PeriodicMonitor(m.period, m.offset, key, bus, m.min_time, m.max_time))


_MONITOR_HANDLERS: dict[MonitorType, _MonitorHandler] = {
    MonitorType.PERIODIC: _compile_periodic,
    MonitorType.ABILITY: _compile_ability,
    MonitorType.ITEM:  _compile_item,
    MonitorType.MIDAS: _compile_midas,
    MonitorType.BLINK: _compile_blink,
    MonitorType.MAP:   _compile_map,
    MonitorType.HERO:  _compile_hero,
}


def compile_rules(rules: list[Rule], bus: RuleEventBus) -> CompiledRules:
    compiled = CompiledRules()

    for rule in rules:
        m = rule.monitor
        actions = _enabled(rule.actions)
        if not actions:
            continue
        ctx = EventContext(rule_id=rule.id, monitor_type=m.type, event_name=m.event)
        _MONITOR_HANDLERS[m.type](rule, m, actions, bus, ctx, compiled)

    return compiled
