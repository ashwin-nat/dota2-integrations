from __future__ import annotations

from typing import TYPE_CHECKING

from src.state.items import BaseItem, EmptyItem, NoChargeItem, SingleChargeItem, MultiChargeItem

if TYPE_CHECKING:
    from src.rules.bus import RuleEventBus


class ItemMonitor:
    """Base class for item monitors compiled from rules."""

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        self._event_key = event_key
        self._bus = bus

    def evaluate(self, curr: BaseItem, prev: BaseItem | None) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        pass


class CooldownReadyMonitor(ItemMonitor):
    """Fires when cooldown transitions from > 0 to 0 (item becomes castable)."""

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, curr: BaseItem, prev: BaseItem | None) -> None:
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
    """Fires when cooldown transitions from 0 to > 0 (item was used)."""

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(event_key, bus)
        self._prev_cooldown: int | None = None

    def evaluate(self, curr: BaseItem, prev: BaseItem | None) -> None:
        cooldown = _get_cooldown(curr)
        if cooldown is None:
            self._prev_cooldown = None
            return
        if self._prev_cooldown is not None and self._prev_cooldown == 0 and cooldown > 0:
            self._bus.emit(self._event_key)
        self._prev_cooldown = cooldown

    def clear(self) -> None:
        self._prev_cooldown = None


class ItemAcquiredMonitor(ItemMonitor):
    """Fires once when the item appears in the slot for the first time."""

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(event_key, bus)
        self._seen: bool = False

    def evaluate(self, curr: BaseItem, prev: BaseItem | None) -> None:
        if not self._seen and not isinstance(curr, EmptyItem):
            self._seen = True
            self._bus.emit(self._event_key)

    def clear(self) -> None:
        self._seen = False


class ItemLostMonitor(ItemMonitor):
    """Fires when the item slot transitions from a named item to empty."""

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(event_key, bus)
        self._had_item: bool = False

    def evaluate(self, curr: BaseItem, prev: BaseItem | None) -> None:
        has_item = not isinstance(curr, EmptyItem)
        if self._had_item and not has_item:
            self._bus.emit(self._event_key)
        self._had_item = has_item

    def clear(self) -> None:
        self._had_item = False


class MidasChargedMonitor(ItemMonitor):
    """Fires when Midas gains a charge (0 → 1)."""

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(event_key, bus)
        self._prev_charges: int | None = None

    def evaluate(self, curr: BaseItem, prev: BaseItem | None) -> None:
        if not isinstance(curr, MultiChargeItem):
            self._prev_charges = None
            return
        if self._prev_charges is not None and self._prev_charges == 0 and curr.charges == 1:
            self._bus.emit(self._event_key)
        self._prev_charges = curr.charges

    def clear(self) -> None:
        self._prev_charges = None


class MidasOverchargedMonitor(ItemMonitor):
    """Fires when Midas reaches 2 charges."""

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        super().__init__(event_key, bus)
        self._prev_charges: int | None = None

    def evaluate(self, curr: BaseItem, prev: BaseItem | None) -> None:
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


def _get_cooldown(item: BaseItem) -> int | None:
    if isinstance(item, (NoChargeItem, SingleChargeItem, MultiChargeItem)):
        return item.cooldown
    return None
