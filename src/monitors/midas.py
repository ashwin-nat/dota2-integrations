from __future__ import annotations

from typing import TYPE_CHECKING

from src.events import EventBus, EventCode
from src.state.items import MultiChargeItem

if TYPE_CHECKING:
    from src.state.store import GameState


class MidasMonitor:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._old_charges: int | None = None
        self._had_midas: bool = False

    async def update(self, state: GameState) -> None:
        if not state.items:
            return

        found = False
        for item in state.items:
            if not isinstance(item, MultiChargeItem) or item.name != "item_hand_of_midas":
                continue
            found = True
            if not self._had_midas:
                self._bus.emit(EventCode.MIDAS_PURCHASED, item=item)
            if item.charges == 2 and self._old_charges != 2:
                self._bus.emit(EventCode.MIDAS_OVERCHARGED, item=item)
            if item.charges == 1 and self._old_charges == 0:
                self._bus.emit(EventCode.MIDAS_CHARGED, item=item)
            self._old_charges = item.charges

        self._had_midas = found
