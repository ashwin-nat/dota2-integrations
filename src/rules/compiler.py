from __future__ import annotations

from dataclasses import dataclass, field

from src.rules.bus import RuleEventBus
from src.rules.config import Rule
from src.rules.item_monitors import ITEM_MONITOR_REGISTRY, ItemMonitor


@dataclass
class CompiledRules:
    # maps item name → list of monitors to evaluate for that item
    monitors_by_item: dict[str, list[ItemMonitor]] = field(default_factory=dict)


def compile_rules(rules: list[Rule], bus: RuleEventBus) -> CompiledRules:
    """Compile validated Rule objects into precomputed monitors + bus listeners.

    For each rule:
      1. Build the event key:  "<MONITOR_UPPER>.<EVENT>.<TARGET_NAME>"
      2. Register actions in the bus under that key
      3. Instantiate the appropriate monitor
      4. Index the monitor under monitors_by_item[target.name]
    """
    compiled = CompiledRules()

    for rule in rules:
        event_key = f"{rule.monitor.upper()}.{rule.event}.{rule.target.name}"
        bus.register(event_key, rule.actions)

        monitor = _build_monitor(rule, event_key, bus)
        compiled.monitors_by_item.setdefault(rule.target.name, []).append(monitor)

    return compiled


def _build_monitor(rule: Rule, event_key: str, bus: RuleEventBus) -> ItemMonitor:
    if rule.monitor == "item":
        cls = ITEM_MONITOR_REGISTRY[rule.event]
        return cls(event_key, bus)
    raise ValueError(f"Unknown monitor type: {rule.monitor!r}")
