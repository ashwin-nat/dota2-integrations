from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.rules.bus import EventContext, RuleEventBus
from src.rules.config import (
    AnyAction,
    AnyMonitor,
    BlinkMonitorConfig,
    HeroMonitorConfig,
    ItemMonitorConfig,
    MapMonitorConfig,
    MidasMonitorConfig,
    MonitorType,
    ResetLightAction,
    Rule,
)
from src.rules.item_monitors import BLINK_MONITOR_REGISTRY, ITEM_MONITOR_REGISTRY, ITEM_SPECIFIC_REGISTRIES, MIDAS_MONITOR_REGISTRY, ItemMonitor
from src.rules.map_monitor import MapMonitor
from src.rules.hero_monitor import HeroMonitor


@dataclass
class CompiledRules:
    item_monitors: list[ItemMonitor] = field(default_factory=list)
    map_monitors: list[MapMonitor] = field(default_factory=list)
    hero_monitors: list[HeroMonitor] = field(default_factory=list)


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


def _compile_map(rule: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, MapMonitorConfig)
    for action in actions:
        if isinstance(action, ResetLightAction):
            raise ValueError(f"Rule {rule.id!r}: reset_light cannot be used on map monitors")
    bus.register(m.event_key, actions, ctx)
    compiled.map_monitors.append(MapMonitor(m.event, m.event_key, bus))


def _compile_hero(_: Rule, m: AnyMonitor, actions: list[AnyAction], bus: RuleEventBus, ctx: EventContext, compiled: CompiledRules) -> None:
    assert isinstance(m, HeroMonitorConfig)
    bus.register(m.event_key, actions, ctx)
    compiled.hero_monitors.append(HeroMonitor(m.event, m.event_key, bus))


_MONITOR_HANDLERS: dict[MonitorType, _MonitorHandler] = {
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
