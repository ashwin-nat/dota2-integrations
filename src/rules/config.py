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
    PLAY_RANDOM_SOUND = "play_random_sound"
    LIGHT       = "light"
    WEBHOOK     = "webhook"


class MonitorType(StrEnum):
    ITEM  = "item"
    MIDAS = "midas"
    BLINK = "blink"
    MAP   = "map"
    HERO  = "hero"
    ABILITY = "ability"


# --- Sound config ---

class SoundConfig(BaseModel):
    volume: int = Field(ge=0, le=100, default=100)


# --- Lighting config ---

class LightingVendor(StrEnum):
    TAPO = "tapo"
    TUYA = "tuya"
    LOG  = "log"


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


class RandomSoundClip(BaseModel):
    file: str
    probability: int = Field(ge=0, le=100)
    volume: int = Field(ge=0, le=100, default=100)


class PlayRandomSoundAction(BaseAction):
    type: Literal[ActionType.PLAY_RANDOM_SOUND]
    clips: list[RandomSoundClip] = Field(min_length=1)

    @model_validator(mode="after")
    def probabilities_must_sum_to_100(self) -> PlayRandomSoundAction:
        total = sum(c.probability for c in self.clips)
        if total != 100:
            raise ValueError(f"clip probabilities must sum to 100, got {total}")
        return self


class LightAction(BaseAction):
    type: Literal[ActionType.LIGHT]
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)
    # Higher wins and doubles as the request's identity, so it must be unique
    # across rules. Required on every non-map rule; must be unset on map
    # monitors, which always use the hard-coded baseline (priority 0).
    priority: int | None = Field(ge=1, default=None)


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
    Union[PlaySoundAction, PlayRandomSoundAction, LightAction, WebhookAction],
    Field(discriminator="type"),
]


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


class AbilityMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.ABILITY]
    target: str  # internal ability name, e.g. "spectre_spectral_dagger"
    event: Literal["COOLDOWN_STARTED"]

    @property
    def event_key(self) -> str:
        return f"__ABILITY__{self.event}__{self.target}__"


AnyMonitor = Annotated[
    Union[ItemMonitorConfig, MidasMonitorConfig, BlinkMonitorConfig, MapMonitorConfig, HeroMonitorConfig, AbilityMonitorConfig],
    Field(discriminator="type"),
]


# --- Rule ---

class Rule(BaseModel):
    id: str
    monitor: AnyMonitor
    actions: list[AnyAction]

    # Checked here rather than on the action so the error can name the rule
    @model_validator(mode="after")
    def sound_files_must_exist(self) -> Rule:
        for action in self.actions:
            if isinstance(action, PlaySoundAction) and not Path(action.file).is_file():
                raise ValueError(f"Rule {self.id!r}: sound file not found: {action.file!r}")
            if isinstance(action, PlayRandomSoundAction):
                for clip in action.clips:
                    if not Path(clip.file).is_file():
                        raise ValueError(f"Rule {self.id!r}: sound file not found: {clip.file!r}")
        return self


# --- Top-level config ---

class RulesConfig(BaseModel):
    rules: list[Rule] = Field(default_factory=list)
    sound: SoundConfig = Field(default_factory=SoundConfig)
    lighting: LightingConfig = Field(default_factory=LightingConfig)

    @model_validator(mode="after")
    def validate_light_priorities(self) -> RulesConfig:
        seen: dict[int, str] = {}
        for rule in self.rules:
            for action in rule.actions:
                if not (isinstance(action, LightAction) and action.enabled):
                    continue
                if rule.monitor.type == MonitorType.MAP:
                    if action.priority is not None:
                        raise ValueError(
                            f"Rule {rule.id!r}: priority cannot be set on map monitors (they are the baseline)"
                        )
                    continue
                if action.priority is None:
                    raise ValueError(f"Rule {rule.id!r}: light action requires a priority")
                if action.priority in seen:
                    raise ValueError(
                        f"Rule {rule.id!r}: light priority {action.priority} already used by rule {seen[action.priority]!r}"
                    )
                seen[action.priority] = rule.id
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
