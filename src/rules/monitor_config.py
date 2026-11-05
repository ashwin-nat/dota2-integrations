from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.monitor_base import Monitor


class MonitorType(StrEnum):
    ITEM  = "item"
    MIDAS = "midas"
    BLINK = "blink"
    MAP   = "map"
    HERO  = "hero"
    ABILITY = "ability"
    PERIODIC = "periodic"
    ONCE = "once"


class MonitorConfig(BaseModel):
    """Base for the `monitor` block of a rule.

    Each monitor module defines its own subclass next to its monitor class. The
    `AnyMonitor` union in `config.py` is the one place that lists them all.
    """
    type: MonitorType

    # Map monitors set the baseline colour, so their light actions must not carry a priority;
    # every other monitor requires one.
    takes_light_priority: ClassVar[bool] = True

    def build(self, bus: EventBus, key: str) -> Monitor:
        """Create the runtime monitor for this config, tagged with its type.

        `key` is the bus key the monitor publishes under. The compiler passes the
        rule's id, so every rule has its own monitor and two rules on the same
        trigger never share (or double-fire) each other's actions.
        """
        monitor = self._create(bus, key)
        monitor.type = self.type
        return monitor

    @abstractmethod
    def _create(self, bus: EventBus, key: str) -> Monitor:
        """Construct the runtime monitor."""
