from __future__ import annotations

from typing import TYPE_CHECKING

from src.state.items import BaseItem, EmptyItem, NoChargeItem, SingleChargeItem, MultiChargeItem, Items

if TYPE_CHECKING:
    from src.rules.bus import RuleEventBus


class ItemMonitor:
    """Base class for item monitors compiled from rules.

    Each monitor receives the full Items snapshot (current and previous) and
    is responsible for finding its target item by name across all slots.
    """

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        self._target = target
        self._event_key = event_key
        self._bus = bus

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        pass


def _find_item(items: Items, name: str) -> BaseItem | None:
    """Return the first non-empty slot holding the named item, or None."""
    for item in items:
        if not isinstance(item, EmptyItem) and item.name == name:
            return item
    return None


class CooldownReadyMonitor(ItemMonitor):
    """Fires when the target item's cooldown transitions from > 0 to 0."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
        cooldown = _get_cooldown(curr)
        if cooldown is None:
            self._prev_cooldown = None
            return
        if self._prev_cooldown is not None and self._prev_cooldown > 0 and cooldown == 0:
            self._bus.emit(self._event_key)
        self._prev_cooldown = cooldown

    def clear(self) -> None:
        self._prev_cooldown = None


class CooldownStartedMonitor(ItemMonitor):
    """Fires when the target item's cooldown transitions from 0 to > 0."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
        cooldown = _get_cooldown(curr)
        if cooldown is None:
            self._prev_cooldown = None
            return
        assert isinstance(curr, (NoChargeItem, SingleChargeItem, MultiChargeItem))
        max_cd = curr.max_cooldown - 1 # Game seems to report max cooldown as 1 higher than actual for some reason
        if self._prev_cooldown is not None and self._prev_cooldown == 0 and cooldown == max_cd:
            print(f"Emitting {self._event_key} because cooldown started (was {self._prev_cooldown}, now {cooldown})")
            print(f"Item state: {curr}")
            self._bus.emit(self._event_key)
        self._prev_cooldown = cooldown

    def clear(self) -> None:
        self._prev_cooldown = None


class ItemAcquiredMonitor(ItemMonitor):
    """Fires once when the target item appears anywhere in the inventory."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._seen: bool = False

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        found = _find_item(items, self._target) is not None
        if not found:
            self._seen = False
        elif not self._seen:
            self._seen = True
            self._bus.emit(self._event_key)

    def clear(self) -> None:
        self._seen = False


class ItemLostMonitor(ItemMonitor):
    """Fires when the target item disappears from the inventory."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._had_item: bool = False

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        has_item = _find_item(items, self._target) is not None
        if self._had_item and not has_item:
            self._bus.emit(self._event_key)
        self._had_item = has_item

    def clear(self) -> None:
        self._had_item = False


class MidasChargedMonitor(ItemMonitor):
    """Fires when Midas transitions to single charge (both 2 -> 1 and 0 -> 1)."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_charges: int | None = None

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
        if not isinstance(curr, MultiChargeItem):
            self._prev_charges = None
            return
        if self._prev_charges is not None and self._prev_charges != curr.charges and curr.charges == 1:
            self._bus.emit(self._event_key)
        self._prev_charges = curr.charges

    def clear(self) -> None:

        self._prev_charges = None


class MidasOverchargedMonitor(ItemMonitor):
    """Fires when Midas reaches 2 charges."""

    def __init__(self, target: str, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_charges: int | None = None

    def evaluate(self, items: Items, prev_items: Items | None) -> None:
        curr = _find_item(items, self._target)
        if not isinstance(curr, MultiChargeItem):
            self._prev_charges = None
            return
        if self._prev_charges is not None and self._prev_charges != 2 and curr.charges == 2:
            self._bus.emit(self._event_key)
        self._prev_charges = curr.charges

    def clear(self) -> None:
        self._prev_charges = None


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


def _get_cooldown(item: BaseItem | None) -> int | None:
    if isinstance(item, (NoChargeItem, SingleChargeItem, MultiChargeItem)):
        return item.cooldown
    return None
