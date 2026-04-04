from __future__ import annotations

from typing import TYPE_CHECKING

from src.events import EventBus, EventCode
from src.state.items import MultiChargeItem

if TYPE_CHECKING:
    from src.state.store import GameState


class MidasChargeMonitor:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._old_charges: int | None = None

    async def update(self, state: GameState) -> None:
        if not state.items:
            return
        for item in state.items:
            if not isinstance(item, MultiChargeItem) or item.name != "item_hand_of_midas":
                continue
            if item.charges == 2 and self._old_charges != 2:
                self._bus.emit(EventCode.MIDAS_OVERCHARGED, slot_id=item.slot_id, charges=item.charges)
                print(f"Midas overcharged in slot {item.slot_id}!")
            if item.charges == 1 and self._old_charges == 0:
                self._bus.emit(EventCode.MIDAS_CHARGED, slot_id=item.slot_id, charges=item.charges)
                print(f"Midas charged in slot {item.slot_id}!")
            self._old_charges = item.charges
