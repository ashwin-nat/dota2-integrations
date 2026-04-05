from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# --- Actions ---

class PlaySoundAction(BaseModel):
    type: Literal["play_sound"]
    file: str


class PrintAction(BaseModel):
    type: Literal["print"]
    message: str = ""


Action = Annotated[
    Union[PlaySoundAction, PrintAction],
    Field(discriminator="type"),
]


# --- Rule target ---

class ItemTarget(BaseModel):
    name: str


# --- Rule ---

class Rule(BaseModel):
    id: str
    monitor: Literal["item"]
    event: Literal["COOLDOWN_READY", "COOLDOWN_STARTED", "ITEM_ACQUIRED", "ITEM_LOST"]
    target: ItemTarget
    actions: list[Action]


# --- Top-level config ---

class RulesConfig(BaseModel):
    rules: list[Rule]

    @classmethod
    def from_list(cls, data: list) -> RulesConfig:
        """Parse a JSON array (the root-level format) into a RulesConfig."""
        return cls.model_validate({"rules": data})
