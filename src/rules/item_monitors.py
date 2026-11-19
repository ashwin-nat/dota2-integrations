from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from src.rules.monitor_base import StateSnapshot, TargetedMonitorConfig, TargetedStatefulMonitor
from src.rules.monitor_config import MonitorType
from src.state.items import BaseItem, NoChargeItem, SingleChargeItem, MultiChargeItem

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.config import Rule

logger = logging.getLogger(__name__)


class ItemMonitorConfig(TargetedMonitorConfig):
    """Item events. Items with their own class for an event (Blink, BKB) set `for_target` on it."""
    type: Literal[MonitorType.ITEM]
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]


class MidasMonitorConfig(TargetedMonitorConfig):
    """Monitor for Hand of Midas charge-specific events.

    Why its own type: what matters for Midas is its charge count (0-2), which the generic item
    events (cooldown, in inventory) don't look at. Midas bought/lost still uses the `item` type.
    """
    type: Literal[MonitorType.MIDAS]
    target: Literal["item_hand_of_midas"] = Field("item_hand_of_midas", exclude=True)
    event: Literal["CHARGED", "OVERCHARGED"]


class BlinkMonitorConfig(TargetedMonitorConfig):
    """Monitor for Blink Dagger item events: an `item` rule on item_blink, with its own editor entry.

    Why its own type: only so Blink gets its own card in the editor. The behaviour lives in the
    item classes (`uses_classes_of`), with BlinkCooldownStartedMonitor for its cancel penalty.
    """
    type: Literal[MonitorType.BLINK]
    target: Literal["item_blink"] = Field("item_blink", exclude=True)
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]
    uses_classes_of = MonitorType.ITEM


class CooldownReadyMonitor(TargetedStatefulMonitor):
    """Active while the target item is off cooldown, from the > 0 to 0 transition."""
    for_type = MonitorType.ITEM
    for_event = "COOLDOWN_READY"

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
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
    for_type = MonitorType.ITEM
    for_event = "COOLDOWN_STARTED"

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
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
    for_type = MonitorType.ITEM
    for_event = "ITEM_ACQUIRED"

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
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
    for_type = MonitorType.ITEM
    for_event = "ITEM_LOST"

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
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
    for_type = MonitorType.MIDAS
    for_event = "CHARGED"

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
    for_type = MonitorType.MIDAS
    for_event = "OVERCHARGED"

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


class BlinkCooldownStartedMonitor(CooldownStartedMonitor):
    """Fires when Blink Dagger is used (cooldown 0 -> >0), ignoring cancel-penalty cooldowns (max_cooldown==4).

    Why its own class: taking damage puts Blink on a 3 s cooldown without it being used, which
    the generic item monitor would read as a cast.
    """
    for_target = "item_blink"

    def _started(self, curr: NoChargeItem | SingleChargeItem | MultiChargeItem, cooldown: int) -> bool:
        # When the player gets hit, blink gets cancelled for 3 sec (game for whatever reason reprots it as 4)
        cancelled = curr.max_cooldown == 4
        return not cancelled and self._prev_cooldown == 0 and cooldown > 0


# GSI does not report the BKB buff, so approximate it as the first N seconds of the cooldown.
BKB_BUFF_SECONDS = 10


class BkbCooldownStartedMonitor(CooldownStartedMonitor):
    """Active for the BKB buff window after use, not the whole cooldown.

    Why its own class: the generic monitor stays active for the whole cooldown, so a BKB light
    would outlast the buff by a minute. It also counts a refresh + reuse within one update as a use.

    Since the incoming data does not contain buff info,
    The buff window is measured on the item's own cooldown (which counts down in game
    time, so pausing is respected) and ends early if the item is lost.
    """
    for_target = "item_black_king_bar"

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
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


def _get_cooldown(item: BaseItem | None) -> int | None:
    if isinstance(item, (NoChargeItem, SingleChargeItem, MultiChargeItem)):
        return item.cooldown
    return None
