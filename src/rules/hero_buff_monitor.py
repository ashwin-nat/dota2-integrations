from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from src.rules.monitor_base import StateSnapshot, StatefulMonitor
from src.rules.monitor_config import MonitorConfig, MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.config import Rule

class HeroBuffMonitorConfig(MonitorConfig):
    """Fires the moment the stack count of one permanent buff (`buff`) goes up or down.

    The backend does not know which buffs only grow (Tidehunter's Leviathan's Catch) and which
    also lose stacks (Muerta's Supernatural); that takes Dota knowledge, so the editor decides
    which events to offer for each buff.
    """
    type: Literal[MonitorType.HERO_BUFF]
    buff: str  # modifier name from hero.permanent_buffs, e.g. "modifier_muerta_supernatural"
    event: Literal["STACK_GAINED", "STACK_LOST"] = "STACK_GAINED"

    def _create(self, bus: EventBus, rule: Rule) -> HeroBuffMonitor:
        return HeroBuffMonitor(rule, bus)


class HeroBuffMonitor(StatefulMonitor):
    """Fires when a permanent buff's stacks rise (STACK_GAINED) or fall (STACK_LOST), ends on the next update.

    A missing key counts as 0 (Leviathan's Catch goes `{}` -> 1; Muerta starts at 0). A gap
    that spans several steps fires once. The first update only records the count, so joining
    mid-match with stacks already there is silent. A drop only fires STACK_LOST rules.
    """

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
        cfg = cast("HeroBuffMonitorConfig", rule.monitor)
        self._buff, self._gained = cfg.buff, cfg.event == "STACK_GAINED"
        self._prev: int | None = None

    def evaluate(self, snap: StateSnapshot) -> None:
        hero = snap.hero
        if hero is None:
            return
        current = hero.permanent_buffs.get(self._buff, 0)
        self._end()
        prev = self._prev
        if prev is not None:
            if current > prev and self._gained:
                self._fire()
            elif current < prev and not self._gained:
                self._fire()
        self._prev = current

    def clear(self) -> None:
        super().clear()
        self._prev = None
