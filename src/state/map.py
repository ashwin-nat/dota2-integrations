from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MapState:
    name: str
    matchid: str
    game_time: int
    clock_time: int
    daytime: bool
    nightstalker_night: bool
    radiant_score: int
    dire_score: int
    game_state: str
    paused: bool
    win_team: str
    customgamename: str
    ward_purchase_cooldown: int


def parse_map(data: dict) -> MapState:
    return MapState(
        name=data["name"],
        matchid=data["matchid"],
        game_time=data["game_time"],
        clock_time=data["clock_time"],
        daytime=data["daytime"],
        nightstalker_night=data["nightstalker_night"],
        radiant_score=data["radiant_score"],
        dire_score=data["dire_score"],
        game_state=data["game_state"],
        paused=data["paused"],
        win_team=data["win_team"],
        customgamename=data["customgamename"],
        ward_purchase_cooldown=data["ward_purchase_cooldown"],
    )
