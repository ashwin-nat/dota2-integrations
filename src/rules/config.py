from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# --- Action types ---

class ActionType(StrEnum):
    PLAY_SOUND  = "play_sound"
    LIGHT       = "light"
    RESET_LIGHT = "reset_light"
    LOGGER      = "logger"


# --- Actions ---

class Action(BaseModel):
    type: ActionType


class PlaySoundAction(Action):
    type: Literal[ActionType.PLAY_SOUND]
    file: str

    @field_validator("file")
    @classmethod
    def file_must_exist(cls, v: str) -> str:
        if not Path(v).is_file():
            raise ValueError(f"sound file not found: {v!r}")
        return v


class LightAction(Action):
    type: Literal[ActionType.LIGHT]
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


class ResetLightAction(Action):
    """Resets lighting to the map-level day/night colour for the current game time.

    Requires ``map_colours`` to be defined in the top-level rules config.
    Cannot be used on map-level monitors (those define the baseline colours).
    """
    type: Literal[ActionType.RESET_LIGHT]


class LoggerAction(Action):
    type: Literal[ActionType.LOGGER]
    message: str


AnyAction = Annotated[
    Union[PlaySoundAction, LightAction, ResetLightAction, LoggerAction],
    Field(discriminator="type"),
]


# --- Map colours ---

class RGB(BaseModel):
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


class MapColours(BaseModel):
    """Day/night baseline colours used by the reset_light action."""
    day: RGB
    night: RGB


# --- Monitor configs ---

class MonitorConfig(BaseModel):
    type: str


class ItemMonitorConfig(MonitorConfig):
    type: Literal["item"]
    target: str
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]

    @property
    def event_key(self) -> str:
        return f"__ITEM__{self.event}__{self.target}__"


class MidasMonitorConfig(MonitorConfig):
    """Monitor for Hand of Midas charge-specific events."""
    type: Literal["midas"]
    event: Literal["CHARGED", "OVERCHARGED"]

    @property
    def event_key(self) -> str:
        return f"__MIDAS__{self.event}__"


class MapMonitorConfig(MonitorConfig):
    type: Literal["map"]
    event: Literal["DAYTIME_STARTED", "NIGHTTIME_STARTED"]

    @property
    def event_key(self) -> str:
        return f"__MAP__{self.event}__"


AnyMonitor = Annotated[
    Union[ItemMonitorConfig, MidasMonitorConfig, MapMonitorConfig],
    Field(discriminator="type"),
]


# --- Rule ---

class Rule(BaseModel):
    id: str
    monitor: AnyMonitor
    actions: list[AnyAction]


# --- Top-level config ---

def _has_reset_light(rules: list[Rule]) -> bool:
    return any(
        isinstance(action, ResetLightAction)
        for rule in rules
        for action in rule.actions
    )


class RulesConfig(BaseModel):
    rules: list[Rule]
    map_colours: MapColours | None = None

    @model_validator(mode="after")
    def reset_light_requires_map_colours(self) -> RulesConfig:
        if _has_reset_light(self.rules) and self.map_colours is None:
            raise ValueError(
                "map_colours must be defined when any rule uses the reset_light action"
            )
        return self

    @classmethod
    def from_file(cls, data: dict) -> RulesConfig:
        """Parse a JSON object with optional ``map_colours`` and ``rules`` keys."""
        return cls.model_validate(data)

    @classmethod
    def from_list(cls, data: list) -> RulesConfig:
        """Parse a JSON array (the root-level format) into a RulesConfig."""
        return cls.model_validate({"rules": data})
