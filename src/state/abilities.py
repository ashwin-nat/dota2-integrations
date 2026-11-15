from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Generator


@dataclass(frozen=True)
class Ability:
    slot_id: str
    name: str
    level: int
    can_cast: bool
    passive: bool
    ability_active: bool
    cooldown: int
    max_cooldown: int
    ultimate: bool


@dataclass(frozen=True)
class ChargeAbility(Ability):
    """Charge shape (Shrapnel, Demonic Purge): the common fields plus three.

    `cooldown` / `max_cooldown` don't track the recharge here (usually 0), so a
    cast is a drop in `charges`; `charge_cooldown` is seconds to the next charge.
    """
    charges: int
    max_charges: int
    charge_cooldown: int


@dataclass(frozen=True)
class Abilities:
    slots: dict[str, Ability]

    @cached_property
    def _by_name(self) -> dict[str, Ability]:
        index: dict[str, Ability] = {}
        for ability in self:
            index.setdefault(ability.name, ability)
        return index

    def find(self, name: str) -> Ability | None:
        """Return the first slot holding the named ability, or None.

        The name index is built on first use, so every monitor evaluating the
        same snapshot shares one pass over the slots.
        """
        return self._by_name.get(name)

    def at(self, slot_id: str) -> Ability | None:
        """Return whatever ability sits in the slot, or None if the slot is absent."""
        return self.slots.get(slot_id)

    def __iter__(self) -> Generator[Ability, None, None]:
        yield from self.slots.values()


def _parse_ability(slot_id: str, data: dict) -> Ability:
    common = dict(
        slot_id=slot_id,
        name=data["name"],
        level=data["level"],
        can_cast=data["can_cast"],
        passive=data["passive"],
        ability_active=data["ability_active"],
        cooldown=data["cooldown"],
        max_cooldown=data["max_cooldown"],
        ultimate=data["ultimate"],
    )
    if "charges" in data:
        return ChargeAbility(
            **common,
            charges=data["charges"],
            max_charges=data["max_charges"],
            charge_cooldown=data["charge_cooldown"],
        )
    return Ability(**common)


def parse_abilities(data: dict) -> Abilities:
    # Slot count varies per hero (e.g. ability0..ability6), so take whatever is present.
    return Abilities(slots={
        key: _parse_ability(key, value)
        for key, value in data.items()
        if key.startswith("ability")
    })
