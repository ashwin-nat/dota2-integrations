from .items import Items, parse_items, MultiChargeItem
from src.events import bus, EventCode


class GameState:
    def __init__(self):
        self._data: dict | None = None
        self._version: int = 0
        self.items: Items | None = None

        self._old_midas_charges: int | None = None

    def get(self) -> dict | None:
        return self._data

    async def set(self, data: dict):
        # store a copy to avoid accidental mutation
        self._data = data.copy()
        self._version += 1
        self.items = parse_items(data["items"]) if "items" in data else None
        await self._on_update()
        await bus.emit(EventCode.STATE_UPDATED, state=self)

    def version(self) -> int:
        return self._version

    async def _on_update(self):
        if not self.items:
            return
        for item in self.items:
            if not isinstance(item, MultiChargeItem):
                continue
            if item.name != "item_hand_of_midas":
                continue

            if item.charges == 2 and self._old_midas_charges != 2:
                await bus.emit(EventCode.MIDAS_OVERCHARGED, slot_id=item.slot_id, charges=item.charges)

            if item.charges == 1 and self._old_midas_charges == 0:
                await bus.emit(EventCode.MIDAS_CHARGED, slot_id=item.slot_id, charges=item.charges)

            self._old_midas_charges = item.charges
