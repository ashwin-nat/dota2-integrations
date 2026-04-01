from .items import Items, parse_items, Item


class GameState:
    def __init__(self):
        self._data: dict | None = None
        self._version: int = 0
        self.items: Items | None = None

        self._old_midas_charges = None
        self._old_midas_cd = None
        self._old_midas_charge_cd = None
        self._old_midas_charges = None

    def get(self) -> dict | None:
        return self._data

    def set(self, data: dict):
        # store a copy to avoid accidental mutation
        self._data = data.copy()
        self._version += 1
        self.items = parse_items(data["items"]) if "items" in data else None
        self._on_update()

    def version(self) -> int:
        return self._version

    def _on_update(self):
        if not self.items:
            return
        for _slot_id, item in self.items.items():
            if not isinstance(item, Item):
                continue

            if not item.name != "item_hand_of_midas":
                if item.charges == 2 and self._old_midas_charges != 2:
                    print("Massive Pidas")

                if item.charges == 1 and self._old_midas_charges == 0:
                    print("Pidas")


            self._old_midas_charges = item.charges
            self._old_midas_cd = item.cooldown
            self._old_midas_charge_cd = item.charge_cooldown
            self._old_midas_charges = item.charges
