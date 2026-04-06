from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeroState:
    facet: int
    id: int
    name: str
    # Fields below are absent during pick phase
    xpos: int | None
    ypos: int | None
    level: int | None
    xp: int | None
    alive: bool | None
    respawn_seconds: int | None
    buyback_cost: int | None
    buyback_cooldown: int | None
    health: int | None
    max_health: int | None
    health_percent: int | None
    mana: int | None
    max_mana: int | None
    mana_percent: int | None
    silenced: bool | None
    stunned: bool | None
    disarmed: bool | None
    magicimmune: bool | None
    hexed: bool | None
    muted: bool | None
    has_break: bool | None
    aghanims_scepter: bool | None
    aghanims_shard: bool | None
    smoked: bool | None
    has_debuff: bool | None
    talent_1: bool | None
    talent_2: bool | None
    talent_3: bool | None
    talent_4: bool | None
    talent_5: bool | None
    talent_6: bool | None
    talent_7: bool | None
    talent_8: bool | None
    attributes_level: int | None


def parse_hero(data: dict) -> HeroState:
    g = data.get
    return HeroState(
        facet=data["facet"],
        id=data["id"],
        name=data["name"],
        xpos=g("xpos"),
        ypos=g("ypos"),
        level=g("level"),
        xp=g("xp"),
        alive=g("alive"),
        respawn_seconds=g("respawn_seconds"),
        buyback_cost=g("buyback_cost"),
        buyback_cooldown=g("buyback_cooldown"),
        health=g("health"),
        max_health=g("max_health"),
        health_percent=g("health_percent"),
        mana=g("mana"),
        max_mana=g("max_mana"),
        mana_percent=g("mana_percent"),
        silenced=g("silenced"),
        stunned=g("stunned"),
        disarmed=g("disarmed"),
        magicimmune=g("magicimmune"),
        hexed=g("hexed"),
        muted=g("muted"),
        has_break=g("break"),
        aghanims_scepter=g("aghanims_scepter"),
        aghanims_shard=g("aghanims_shard"),
        smoked=g("smoked"),
        has_debuff=g("has_debuff"),
        talent_1=g("talent_1"),
        talent_2=g("talent_2"),
        talent_3=g("talent_3"),
        talent_4=g("talent_4"),
        talent_5=g("talent_5"),
        talent_6=g("talent_6"),
        talent_7=g("talent_7"),
        talent_8=g("talent_8"),
        attributes_level=g("attributes_level"),
    )
