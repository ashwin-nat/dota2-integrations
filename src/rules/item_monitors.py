from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.rules.monitor_base import StatefulMonitor
from src.state.items import BaseItem, EmptyItem, NoChargeItem, SingleChargeItem, MultiChargeItem, Items

if TYPE_CHECKING:
    from src.rules.bus import RuleEventBus

logger = logging.getLogger(__name__)


class ItemMonitor(StatefulMonitor):
    """Base class for item monitors compiled from rules.

    Each monitor receives the full Items snapshot (current and previous) and
    is responsible for finding its target item by name across all slots.
    """

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(event_key, bus)
        self._target = target

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        raise NotImplementedError


def _find_item(items: Items, name: str) -> BaseItem | None:
    """Return the first non-empty slot holding the named item, or None."""
    for item in items:
        if not isinstance(item, EmptyItem) and item.name == name:
            return item
    return None


class CooldownReadyMonitor(ItemMonitor):
    """Active while the target item is off cooldown, from the > 0 to 0 transition."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
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


class CooldownStartedMonitor(ItemMonitor):
    """Active while the target item is on cooldown, from the 0 to > 0 transition."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
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


class ItemAcquiredMonitor(ItemMonitor):
    """Active while the target item is anywhere in the inventory."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._seen: bool = False

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        found = _find_item(items, self._target) is not None
        if not found:
            self._seen = False
            self._end()
        elif not self._seen:
            self._seen = True
            self._fire()

    def clear(self) -> None:
        super().clear()
        self._seen = False


class ItemLostMonitor(ItemMonitor):
    """Active from when the target item disappears from the inventory until it returns."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._had_item: bool = False

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        has_item = _find_item(items, self._target) is not None
        if self._had_item and not has_item:
            self._fire()
        elif has_item:
            self._end()
        self._had_item = has_item

    def clear(self) -> None:
        super().clear()
        self._had_item = False


class MidasChargedMonitor(ItemMonitor):
    """Active while Midas has exactly 1 charge, including when first seen at 1 (it is bought with 1).

    Assumes charges never jump 2 -> 0 (would be a game bug).
    """

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
        if isinstance(curr, MultiChargeItem) and curr.charges == 1:
            if not self._active:
                self._fire()
        else:
            self._end()


class MidasOverchargedMonitor(ItemMonitor):
    """Active while Midas has 2 charges."""

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
        if isinstance(curr, MultiChargeItem) and curr.charges == 2:
            if not self._active:
                self._fire()
        else:
            self._end()


# Registry: event name → monitor class
ITEM_MONITOR_REGISTRY: dict[str, type[ItemMonitor]] = {
    "COOLDOWN_READY": CooldownReadyMonitor,
    "COOLDOWN_STARTED": CooldownStartedMonitor,
    "ITEM_ACQUIRED": ItemAcquiredMonitor,
    "ITEM_LOST": ItemLostMonitor,
}

MIDAS_MONITOR_REGISTRY: dict[str, type[ItemMonitor]] = {
    "CHARGED": MidasChargedMonitor,
    "OVERCHARGED": MidasOverchargedMonitor,
}


class BlinkCooldownStartedMonitor(CooldownStartedMonitor):
    """Fires when Blink Dagger is used (cooldown 0 → >0), ignoring cancel-penalty cooldowns (max_cooldown==4)."""

    def _started(self, curr: NoChargeItem | SingleChargeItem | MultiChargeItem, cooldown: int) -> bool:
        # When the player gets hit, blink gets cancelled for 3 sec (game for whatever reason reprots it as 4)
        cancelled = curr.max_cooldown == 4
        return not cancelled and self._prev_cooldown == 0 and cooldown > 0


BLINK_MONITOR_REGISTRY: dict[str, type[ItemMonitor]] = {
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

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._start_cooldown: int = 0

    def _started(self, curr: NoChargeItem | SingleChargeItem | MultiChargeItem, cooldown: int) -> bool:
        # Any jump up to a full cooldown is a new use, including a refresh + reuse
        # landing in one update (cooldown never read as 0). While the window is
        # running this restarts it.
        max_cd = curr.max_cooldown - 1
        return self._prev_cooldown is not None and cooldown > self._prev_cooldown and cooldown == max_cd

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
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


BKB_MONITOR_REGISTRY: dict[str, type[ItemMonitor]] = {
    "COOLDOWN_READY": CooldownReadyMonitor,
    "COOLDOWN_STARTED": BkbCooldownStartedMonitor,
    "ITEM_ACQUIRED": ItemAcquiredMonitor,
    "ITEM_LOST": ItemLostMonitor,
}

# Maps item names that have a dedicated registry to that registry.
# Items not listed here fall back to ITEM_MONITOR_REGISTRY.
ITEM_SPECIFIC_REGISTRIES: dict[str, dict[str, type[ItemMonitor]]] = {
    "item_blink": BLINK_MONITOR_REGISTRY,
    "item_black_king_bar": BKB_MONITOR_REGISTRY,
}


def _get_cooldown(item: BaseItem | None) -> int | None:
    if isinstance(item, (NoChargeItem, SingleChargeItem, MultiChargeItem)):
        return item.cooldown
    return None
