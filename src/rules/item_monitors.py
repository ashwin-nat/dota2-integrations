from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from src.rules.monitor_base import StateSnapshot, TargetedStatefulMonitor
from src.rules.monitor_config import MonitorConfig, MonitorType
from src.state.items import BaseItem, NoChargeItem, SingleChargeItem, MultiChargeItem

if TYPE_CHECKING:
    from src.rules.bus import EventBus

logger = logging.getLogger(__name__)


class ItemMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.ITEM]
    target: str
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]

    def _create(self, bus: EventBus, key: str) -> TargetedStatefulMonitor:
        registry = ITEM_SPECIFIC_REGISTRIES.get(self.target, ITEM_MONITOR_REGISTRY)
        return registry[self.event](self.target, key, bus)


class MidasMonitorConfig(MonitorConfig):
    """Monitor for Hand of Midas charge-specific events."""
    type: Literal[MonitorType.MIDAS]
    event: Literal["CHARGED", "OVERCHARGED"]

    def _create(self, bus: EventBus, key: str) -> TargetedStatefulMonitor:
        return MIDAS_MONITOR_REGISTRY[self.event]("item_hand_of_midas", key, bus)


class BlinkMonitorConfig(MonitorConfig):
    """Monitor for Blink Dagger item events."""
    type: Literal[MonitorType.BLINK]
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]

    def _create(self, bus: EventBus, key: str) -> TargetedStatefulMonitor:
        return BLINK_MONITOR_REGISTRY[self.event]("item_blink", key, bus)


class CooldownReadyMonitor(TargetedStatefulMonitor):
    """Active while the target item is off cooldown, from the > 0 to 0 transition."""

    def __init__(self, target: str, event_key: str, bus: EventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, snap: StateSnapshot) -> None:
        items = snap.items
        if items is None:
            return
        curr = items.find(self._target)
        cooldown = _get_cooldown(curr)
        if cooldown is None:
            self._prev_cooldown = None
            self._end()
            return
        if self._prev_cooldown is not None and self._prev_cooldown > 0 and cooldown == 0:
            self._fire()
        elif cooldown > 0:
            self._end()
        self._prev_cooldown = cooldown

    def clear(self) -> None:
        super().clear()
        self._prev_cooldown = None


class CooldownStartedMonitor(TargetedStatefulMonitor):
    """Active while the target item is on cooldown, from the 0 to > 0 transition."""

    def __init__(self, target: str, event_key: str, bus: EventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, snap: StateSnapshot) -> None:
        items = snap.items
        if items is None:
            return
        curr = items.find(self._target)
        cooldown = _get_cooldown(curr)
        if cooldown is None:
            self._prev_cooldown = None
            self._end()
            return
        assert isinstance(curr, (NoChargeItem, SingleChargeItem, MultiChargeItem))
        if self._started(curr, cooldown):
            logger.info(f"Emitting {self._event_key} because cooldown started (was {self._prev_cooldown}, now {cooldown})")
            logger.info(f"Item state: {curr}")
            self._fire()
        elif cooldown == 0:
            self._end()
        self._prev_cooldown = cooldown

    def _started(self, curr: NoChargeItem | SingleChargeItem | MultiChargeItem, cooldown: int) -> bool:
        max_cd = curr.max_cooldown - 1 # Game seems to report max cooldown as 1 higher than actual for some reason
        return self._prev_cooldown == 0 and cooldown == max_cd

    def clear(self) -> None:
        super().clear()
        self._prev_cooldown = None


class ItemAcquiredMonitor(TargetedStatefulMonitor):
    """Active while the target item is anywhere in the inventory."""

    def __init__(self, target: str, event_key: str, bus: EventBus) -> None:
        super().__init__(target, event_key, bus)
        self._seen: bool = False

    def evaluate(self, snap: StateSnapshot) -> None:
        items = snap.items
        if items is None:
            return
        found = items.find(self._target) is not None
        if not found:
            self._seen = False
            self._end()
        elif not self._seen:
            self._seen = True
            self._fire()

    def clear(self) -> None:
        super().clear()
        self._seen = False


class ItemLostMonitor(TargetedStatefulMonitor):
    """Active from when the target item disappears from the inventory until it returns."""

    def __init__(self, target: str, event_key: str, bus: EventBus) -> None:
        super().__init__(target, event_key, bus)
        self._had_item: bool = False

    def evaluate(self, snap: StateSnapshot) -> None:
        items = snap.items
        if items is None:
            return
        has_item = items.find(self._target) is not None
        if self._had_item and not has_item:
            self._fire()
        elif has_item:
            self._end()
        self._had_item = has_item

    def clear(self) -> None:
        super().clear()
        self._had_item = False


class MidasChargedMonitor(TargetedStatefulMonitor):
    """Active while Midas has exactly 1 charge, including when first seen at 1 (it is bought with 1).

    Assumes charges never jump 2 -> 0 (would be a game bug).
    """

    def evaluate(self, snap: StateSnapshot) -> None:
        items = snap.items
        if items is None:
            return
        curr = items.find(self._target)
        if isinstance(curr, MultiChargeItem) and curr.charges == 1:
            if not self._active:
                self._fire()
        else:
            self._end()


class MidasOverchargedMonitor(TargetedStatefulMonitor):
    """Active while Midas has 2 charges."""

    def evaluate(self, snap: StateSnapshot) -> None:
        items = snap.items
        if items is None:
            return
        curr = items.find(self._target)
        if isinstance(curr, MultiChargeItem) and curr.charges == 2:
            if not self._active:
                self._fire()
        else:
            self._end()


# Registry: event name → monitor class
ITEM_MONITOR_REGISTRY: dict[str, type[TargetedStatefulMonitor]] = {
    "COOLDOWN_READY": CooldownReadyMonitor,
    "COOLDOWN_STARTED": CooldownStartedMonitor,
    "ITEM_ACQUIRED": ItemAcquiredMonitor,
    "ITEM_LOST": ItemLostMonitor,
}

MIDAS_MONITOR_REGISTRY: dict[str, type[TargetedStatefulMonitor]] = {
    "CHARGED": MidasChargedMonitor,
    "OVERCHARGED": MidasOverchargedMonitor,
}


class BlinkCooldownStartedMonitor(CooldownStartedMonitor):
    """Fires when Blink Dagger is used (cooldown 0 → >0), ignoring cancel-penalty cooldowns (max_cooldown==4)."""

    def _started(self, curr: NoChargeItem | SingleChargeItem | MultiChargeItem, cooldown: int) -> bool:
        # When the player gets hit, blink gets cancelled for 3 sec (game for whatever reason reprots it as 4)
        cancelled = curr.max_cooldown == 4
        return not cancelled and self._prev_cooldown == 0 and cooldown > 0


BLINK_MONITOR_REGISTRY: dict[str, type[TargetedStatefulMonitor]] = {
    "COOLDOWN_READY": CooldownReadyMonitor,
    "COOLDOWN_STARTED": BlinkCooldownStartedMonitor,
    "ITEM_ACQUIRED": ItemAcquiredMonitor,
    "ITEM_LOST": ItemLostMonitor,
}

# GSI does not report the BKB buff, so approximate it as the first N seconds of the cooldown.
BKB_BUFF_SECONDS = 10


class BkbCooldownStartedMonitor(CooldownStartedMonitor):
    """Active for the BKB buff window after use, not the whole cooldown.

    Since the incoming data does not contain buff info,
    The buff window is measured on the item's own cooldown (which counts down in game
    time, so pausing is respected) and ends early if the item is lost.
    """

    def __init__(self, target: str, event_key: str, bus: EventBus) -> None:
        super().__init__(target, event_key, bus)
        self._start_cooldown: int = 0

    def _started(self, curr: NoChargeItem | SingleChargeItem | MultiChargeItem, cooldown: int) -> bool:
        # Any jump up to a full cooldown is a new use, including a refresh + reuse
        # landing in one update (cooldown never read as 0). While the window is
        # running this restarts it.
        max_cd = curr.max_cooldown - 1
        return self._prev_cooldown is not None and cooldown > self._prev_cooldown and cooldown == max_cd

    def evaluate(self, snap: StateSnapshot) -> None:
        items = snap.items
        if items is None:
            return
        curr = items.find(self._target)
        cooldown = _get_cooldown(curr)
        if cooldown is None:
            self._prev_cooldown = None
            self._end()
            return
        assert isinstance(curr, (NoChargeItem, SingleChargeItem, MultiChargeItem))
        if self._started(curr, cooldown):
            self._start_cooldown = cooldown
            self._fire()
        elif self._active and (cooldown == 0 or self._start_cooldown - cooldown >= BKB_BUFF_SECONDS):
            self._end()
        self._prev_cooldown = cooldown

    def clear(self) -> None:
        super().clear()
        self._start_cooldown = 0


BKB_MONITOR_REGISTRY: dict[str, type[TargetedStatefulMonitor]] = {
    "COOLDOWN_READY": CooldownReadyMonitor,
    "COOLDOWN_STARTED": BkbCooldownStartedMonitor,
    "ITEM_ACQUIRED": ItemAcquiredMonitor,
    "ITEM_LOST": ItemLostMonitor,
}

# Maps item names that have a dedicated registry to that registry.
# Items not listed here fall back to ITEM_MONITOR_REGISTRY.
ITEM_SPECIFIC_REGISTRIES: dict[str, dict[str, type[TargetedStatefulMonitor]]] = {
    "item_blink": BLINK_MONITOR_REGISTRY,
    "item_black_king_bar": BKB_MONITOR_REGISTRY,
}


def _get_cooldown(item: BaseItem | None) -> int | None:
    if isinstance(item, (NoChargeItem, SingleChargeItem, MultiChargeItem)):
        return item.cooldown
    return None
