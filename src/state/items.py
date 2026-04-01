from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class EmptyItem:
    slot_id: str
    name: Literal["empty"] = "empty"


@dataclass(frozen=True)
class Item:
    slot_id: str
    name: str
    purchaser: int
    item_level: int
    can_cast: bool
    cooldown: int
    max_cooldown: int
    passive: bool
    item_charges: int
    charges: int
    ability_charges: int | None = None
    max_charges: int | None = None
    charge_cooldown: int | None = None


ItemSlot = Item | EmptyItem

# dict keyed by slot_id (e.g. "slot0", "stash2", "teleport0")
Items = dict[str, ItemSlot]


def _parse_slot(slot_id: str, data: dict) -> ItemSlot:
    if data.get("name") == "empty":
        return EmptyItem(slot_id=slot_id)
    return Item(
        slot_id=slot_id,
        name=data["name"],
        purchaser=data["purchaser"],
        item_level=data["item_level"],
        can_cast=data["can_cast"],
        cooldown=data["cooldown"],
        max_cooldown=data["max_cooldown"],
        passive=data["passive"],
        item_charges=data["item_charges"],
        charges=data["charges"],
        ability_charges=data.get("ability_charges"),
        max_charges=data.get("max_charges"),
        charge_cooldown=data.get("charge_cooldown"),
    )


def parse_items(data: dict) -> Items:
    return {slot_id: _parse_slot(slot_id, slot_data) for slot_id, slot_data in data.items()}
