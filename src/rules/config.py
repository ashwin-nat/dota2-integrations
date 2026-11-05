from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Union
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from src.media import resolve
from src.rules.ability_monitors import AbilityMonitorConfig
from src.rules.hero_monitor import HeroMonitorConfig
from src.rules.item_monitors import BlinkMonitorConfig, ItemMonitorConfig, MidasMonitorConfig
from src.rules.map_monitor import MapMonitorConfig
from src.rules.periodic_monitor import PeriodicMonitorConfig


# --- Action types ---

class ActionType(StrEnum):
    PLAY_SOUND  = "play_sound"
    LIGHT       = "light"
    WEBHOOK     = "webhook"


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


class SoundClip(BaseModel):
    file: str
    probability: int = Field(ge=0, le=100)
    volume: int = Field(ge=0, le=100, default=100)


class PlaySoundAction(BaseAction):
    """Plays one clip picked by weight; a single clip at probability 100 is a plain sound."""
    type: Literal[ActionType.PLAY_SOUND]
    clips: list[SoundClip] = Field(min_length=1)

    @model_validator(mode="after")
    def probabilities_must_sum_to_100(self) -> PlaySoundAction:
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
    Union[PlaySoundAction, LightAction, WebhookAction],
    Field(discriminator="type"),
]


def sound_refs(action: dict) -> list[str]:
    """Sound files a raw (rules.json) action plays; empty for non-sound actions."""
    if action.get("type") != ActionType.PLAY_SOUND:
        return []
    return [c["file"] for c in action.get("clips", []) if c.get("file")]


# --- Monitor configs ---
# Each monitor's config model lives next to its monitor class. This is the one
# place that lists them all, so pydantic can pick the right one from `type`.

AnyMonitor = Annotated[
    Union[
        ItemMonitorConfig,
        MidasMonitorConfig,
        BlinkMonitorConfig,
        MapMonitorConfig,
        HeroMonitorConfig,
        AbilityMonitorConfig,
        PeriodicMonitorConfig,
    ],
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
            if isinstance(action, PlaySoundAction):
                for clip in action.clips:
                    if not resolve(clip.file).is_file():
                        raise ValueError(f"Rule {self.id!r}: sound file not found: {clip.file!r}")
        return self


# --- Top-level config ---

class RulesConfig(BaseModel):
    rules: list[Rule] = Field(default_factory=list)
    sound: SoundConfig = Field(default_factory=SoundConfig)
    lighting: LightingConfig = Field(default_factory=LightingConfig)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> RulesConfig:
        # A rule's id is the key its monitor publishes under, so it must be unique
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"Rule id {rule.id!r} is used by more than one rule")
            seen.add(rule.id)
        return self

    @model_validator(mode="after")
    def validate_light_priorities(self) -> RulesConfig:
        seen: dict[int, str] = {}
        for rule in self.rules:
            for action in rule.actions:
                if not (isinstance(action, LightAction) and action.enabled):
                    continue
                if not rule.monitor.takes_light_priority:
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
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        config = cls.model_validate(data)
        dumped = config.model_dump()
        if dumped != data:
            path.write_text(json.dumps(dumped, indent=4))
        return config
