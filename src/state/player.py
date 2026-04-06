from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerState:
    steamid: str
    accountid: str
    name: str
    activity: str
    kills: int
    deaths: int
    assists: int
    last_hits: int
    denies: int
    kill_streak: int
    commands_issued: int
    team_name: str
    player_slot: int
    team_slot: int
    gold: int
    gold_reliable: int
    gold_unreliable: int
    gold_from_hero_kills: int
    gold_from_creep_kills: int
    gold_from_income: int
    gold_from_shared: int
    gpm: int
    xpm: int
    # TODO: parse kill_list (dict of recent kills, e.g. {"victimid_0": 1})


def parse_player(data: dict) -> PlayerState:
    return PlayerState(
        steamid=data["steamid"],
        accountid=data["accountid"],
        name=data["name"],
        activity=data["activity"],
        kills=data["kills"],
        deaths=data["deaths"],
        assists=data["assists"],
        last_hits=data["last_hits"],
        denies=data["denies"],
        kill_streak=data["kill_streak"],
        commands_issued=data["commands_issued"],
        team_name=data["team_name"],
        player_slot=data["player_slot"],
        team_slot=data["team_slot"],
        gold=data["gold"],
        gold_reliable=data["gold_reliable"],
        gold_unreliable=data["gold_unreliable"],
        gold_from_hero_kills=data["gold_from_hero_kills"],
        gold_from_creep_kills=data["gold_from_creep_kills"],
        gold_from_income=data["gold_from_income"],
        gold_from_shared=data["gold_from_shared"],
        gpm=data["gpm"],
        xpm=data["xpm"],
    )
