from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class Abilities:
    slots: dict[str, Ability]

    def __iter__(self) -> Generator[Ability, None, None]:
        yield from self.slots.values()


def parse_abilities(data: dict) -> Abilities:
    # Slot count varies per hero (e.g. ability0..ability6), so take whatever is present.
    return Abilities(slots={
        key: Ability(
            slot_id=key,
            name=value["name"],
            level=value["level"],
            can_cast=value["can_cast"],
            passive=value["passive"],
            ability_active=value["ability_active"],
            cooldown=value["cooldown"],
            max_cooldown=value["max_cooldown"],
            ultimate=value["ultimate"],
        )
        for key, value in data.items()
        if key.startswith("ability")
    })
