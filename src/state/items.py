from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, Literal


@dataclass(frozen=True)
class BaseItem:
    slot_id: str


@dataclass(frozen=True)
class EmptyItem(BaseItem):
    name: Literal["empty"] = "empty"


@dataclass(frozen=True)
class PassiveItem(BaseItem):
    name: str
    purchaser: int
    item_level: int
    passive: bool


@dataclass(frozen=True)
class NoChargeItem(BaseItem):
    name: str
    purchaser: int
    item_level: int
    can_cast: bool
    cooldown: int
    max_cooldown: int
    passive: bool


@dataclass(frozen=True)
class SingleChargeItem(BaseItem):
    name: str
    purchaser: int
    item_level: int
    can_cast: bool
    cooldown: int
    max_cooldown: int
    passive: bool
    item_charges: int
    charges: int


@dataclass(frozen=True)
class MultiChargeItem(BaseItem):
    name: str
    purchaser: int
    item_level: int
    can_cast: bool
    cooldown: int
    max_cooldown: int
    passive: bool
    item_charges: int
    ability_charges: int
    max_charges: int
    charge_cooldown: int
    charges: int


@dataclass
class Items:
    _slot0: BaseItem
    _slot1: BaseItem
    _slot2: BaseItem
    _slot3: BaseItem
    _slot4: BaseItem
    _slot5: BaseItem
    _slot6: BaseItem
    _slot7: BaseItem
    _slot8: BaseItem
    _stash0: BaseItem
    _stash1: BaseItem
    _stash2: BaseItem
    _stash3: BaseItem
    _stash4: BaseItem
    _stash5: BaseItem

    def __iter__(self) -> Generator[BaseItem, None, None]:
        yield self._slot0
        yield self._slot1
        yield self._slot2
        yield self._slot3
        yield self._slot4
        yield self._slot5
        yield self._slot6
        yield self._slot7
        yield self._slot8
        yield self._stash0
        yield self._stash1
        yield self._stash2
        yield self._stash3
        yield self._stash4
        yield self._stash5


def _parse_slot(slot_id: str, data: dict) -> BaseItem:
    if data.get("name") == "empty":
        return EmptyItem(slot_id=slot_id)
    if "can_cast" not in data:
        return PassiveItem(
            slot_id=slot_id,
            name=data["name"],
            purchaser=data["purchaser"],
            item_level=data["item_level"],
            passive=data["passive"],
        )
    if "ability_charges" in data:
        return MultiChargeItem(
            slot_id=slot_id,
            name=data["name"],
            purchaser=data["purchaser"],
            item_level=data["item_level"],
            can_cast=data["can_cast"],
            cooldown=data["cooldown"],
            max_cooldown=data["max_cooldown"],
            passive=data["passive"],
            item_charges=data["item_charges"],
            ability_charges=data["ability_charges"],
            max_charges=data["max_charges"],
            charge_cooldown=data["charge_cooldown"],
            charges=data["charges"],
        )
    if "item_charges" in data:
        return SingleChargeItem(
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
        )
    return NoChargeItem(
        slot_id=slot_id,
        name=data["name"],
        purchaser=data["purchaser"],
        item_level=data["item_level"],
        can_cast=data["can_cast"],
        cooldown=data["cooldown"],
        max_cooldown=data["max_cooldown"],
        passive=data["passive"],
    )


def parse_items(data: dict) -> Items:
    def slot(key: str) -> BaseItem:
        return _parse_slot(key, data[key]) if key in data else EmptyItem(slot_id=key)

    return Items(
        _slot0=slot("slot0"),
        _slot1=slot("slot1"),
        _slot2=slot("slot2"),
        _slot3=slot("slot3"),
        _slot4=slot("slot4"),
        _slot5=slot("slot5"),
        _slot6=slot("slot6"),
        _slot7=slot("slot7"),
        _slot8=slot("slot8"),
        _stash0=slot("stash0"),
        _stash1=slot("stash1"),
        _stash2=slot("stash2"),
        _stash3=slot("stash3"),
        _stash4=slot("stash4"),
        _stash5=slot("stash5"),
    )
