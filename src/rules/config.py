from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator


# --- Actions ---

class Action(BaseModel):
    type: str


class PlaySoundAction(Action):
    type: Literal["play_sound"]
    file: str

    @field_validator("file")
    @classmethod
    def file_must_exist(cls, v: str) -> str:
        if not Path(v).is_file():
            raise ValueError(f"sound file not found: {v!r}")
        return v


class LightAction(Action):
    type: Literal["light"]
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


class LoggerAction(Action):
    type: Literal["logger"]
    message: str


AnyAction = Annotated[
    Union[PlaySoundAction, LightAction, LoggerAction],
    Field(discriminator="type"),
]


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


class MapMonitorConfig(MonitorConfig):
    type: Literal["map"]
    event: Literal["DAYTIME_STARTED", "NIGHTTIME_STARTED"]

    @property
    def event_key(self) -> str:
        return f"__MAP__{self.event}__"


AnyMonitor = Annotated[
    Union[ItemMonitorConfig, MapMonitorConfig],
    Field(discriminator="type"),
]


# --- Rule ---

class Rule(BaseModel):
    id: str
    monitor: AnyMonitor
    actions: list[AnyAction]


# --- Top-level config ---

class RulesConfig(BaseModel):
    rules: list[Rule]

    @classmethod
    def from_list(cls, data: list) -> RulesConfig:
        """Parse a JSON array (the root-level format) into a RulesConfig."""
        return cls.model_validate({"rules": data})
