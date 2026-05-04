from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Union
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


# --- Action types ---

class ActionType(StrEnum):
    PLAY_SOUND  = "play_sound"
    LIGHT       = "light"
    RESET_LIGHT = "reset_light"
    LOGGER      = "logger"
    WEBHOOK     = "webhook"


class MonitorType(StrEnum):
    ITEM  = "item"
    MIDAS = "midas"
    BLINK = "blink"
    MAP   = "map"
    HERO  = "hero"


# --- Sound config ---

class SoundConfig(BaseModel):
    volume: int = Field(ge=0, le=100, default=100)


# --- Lighting config ---

class LightingVendor(StrEnum):
    TAPO = "tapo"
    TUYA = "tuya"


class LightingConfig(BaseModel):
    enabled: bool = False
    vendor: LightingVendor = LightingVendor.TAPO


# --- Actions ---

class BaseAction(BaseModel):
    type: ActionType
    enabled: bool = True


class PlaySoundAction(BaseAction):
    type: Literal[ActionType.PLAY_SOUND]
    file: str
    volume: int = Field(ge=0, le=100, default=100)

    @field_validator("file")
    @classmethod
    def file_must_exist(cls, v: str) -> str:
        if not Path(v).is_file():
            raise ValueError(f"sound file not found: {v!r}")
        return v


class LightAction(BaseAction):
    type: Literal[ActionType.LIGHT]
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


class ResetLightAction(BaseAction):
    """Resets lighting to the map-level day/night colour for the current game time.

    Requires ``map_colours`` to be defined in the top-level rules config.
    Cannot be used on map-level monitors (those define the baseline colours).
    """
    type: Literal[ActionType.RESET_LIGHT]


class LoggerAction(BaseAction):
    type: Literal[ActionType.LOGGER]
    message: str


class WebhookAction(BaseAction):
    type: Literal[ActionType.WEBHOOK]
    url: str
    api_key: str | None = None
    auth_type: Literal["bearer", "header", "query"] | None = None
    timeout: float = Field(default=2.0, gt=0)
    cooldown: float = Field(default=0.0, ge=0)

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"url must be a valid HTTP/HTTPS URL, got: {v!r}")
        return v

    @model_validator(mode="after")
    def api_key_requires_auth_type(self) -> WebhookAction:
        if self.api_key is not None and self.auth_type is None:
            raise ValueError("auth_type must be provided when api_key is set")
        return self


AnyAction = Annotated[
    Union[PlaySoundAction, LightAction, ResetLightAction, LoggerAction, WebhookAction],
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
    type: MonitorType


class ItemMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.ITEM]
    target: str
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]

    @property
    def event_key(self) -> str:
        return f"__ITEM__{self.event}__{self.target}__"


class MidasMonitorConfig(MonitorConfig):
    """Monitor for Hand of Midas charge-specific events."""
    type: Literal[MonitorType.MIDAS]
    event: Literal["CHARGED", "OVERCHARGED"]

    @property
    def event_key(self) -> str:
        return f"__MIDAS__{self.event}__"


class BlinkMonitorConfig(MonitorConfig):
    """Monitor for Blink Dagger item events."""
    type: Literal[MonitorType.BLINK]
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]

    @property
    def event_key(self) -> str:
        return f"__BLINK__{self.event}__"


class MapMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.MAP]
    event: Literal["DAYTIME_STARTED", "NIGHTTIME_STARTED", "PAUSED", "UNPAUSED"]

    @property
    def event_key(self) -> str:
        return f"__MAP__{self.event}__"


class HeroMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.HERO]
    event: Literal["HERO_KILLED", "HERO_RESPAWNED"]

    @property
    def event_key(self) -> str:
        return f"__HERO__{self.event}__"


AnyMonitor = Annotated[
    Union[ItemMonitorConfig, MidasMonitorConfig, BlinkMonitorConfig, MapMonitorConfig, HeroMonitorConfig],
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
        if action.enabled
    )


class RulesConfig(BaseModel):
    rules: list[Rule] = Field(default_factory=list)
    map_colours: MapColours | None = None
    sound: SoundConfig = Field(default_factory=SoundConfig)
    lighting: LightingConfig = Field(default_factory=LightingConfig)

    @model_validator(mode="after")
    def reset_light_requires_map_colours(self) -> RulesConfig:
        if _has_reset_light(self.rules) and self.map_colours is None:
            raise ValueError(
                "map_colours must be defined when any rule uses the reset_light action"
            )
        return self

    @classmethod
    def load(cls, path: Path) -> RulesConfig:
        """Load and parse rules.json, writing back any missing keys with their defaults."""
        if not path.exists():
            config = cls()
            path.write_text(config.model_dump_json(indent=4))
            return config
        raw = path.read_text()
        data = json.loads(raw)
        config = cls.model_validate(data)
        dumped = config.model_dump()
        if dumped != data:
            path.write_text(json.dumps(dumped, indent=4))
        return config
