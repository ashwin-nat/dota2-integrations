from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING, Literal, cast

from pydantic import computed_field, field_validator

from src.rules.monitor_base import StateSnapshot, StatefulMonitor
from src.rules.monitor_config import MonitorConfig, MonitorType
from src.state.hero import HeroState

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.config import Rule


# Hero flags a hero_bool rule can watch. `alive` is left out: it keeps the legacy `hero` config
# (HERO_KILLED / HERO_RESPAWNED) and its HeroAliveMonitor subclass.
HERO_BOOL_FIELDS: tuple[str, ...] = tuple(
    f.name for f in fields(HeroState) if f.type == "bool | None" and f.name != "alive"
)


class HeroMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.HERO]
    event: Literal["HERO_KILLED", "HERO_RESPAWNED"]

    def _create(self, bus: EventBus, rule: Rule) -> HeroAliveMonitor:
        return HeroAliveMonitor(rule, bus)


class HeroBoolMonitorConfig(MonitorConfig):
    """Active while one of the hero's true/false flags (`field`) equals `value`, from the change to it."""
    type: Literal[MonitorType.HERO_BOOL]
    field: str  # a HeroState bool, e.g. "stunned" or "aghanims_shard"
    value: bool = True

    @field_validator("field")
    @classmethod
    def field_must_be_a_hero_flag(cls, v: str) -> str:
        if v not in HERO_BOOL_FIELDS:
            raise ValueError(f"field must be one of {', '.join(HERO_BOOL_FIELDS)}, got: {v!r}")
        return v

    # Serialized like every other monitor's `event`, so the editor can tell triggers apart by type + event
    @computed_field  # type: ignore[prop-decorator]
    @property
    def event(self) -> str:
        return f"{self.field.upper()}_{'TRUE' if self.value else 'FALSE'}"

    def _create(self, bus: EventBus, rule: Rule) -> HeroBoolMonitor:
        return HeroBoolMonitor(rule, bus)


class HeroBoolMonitor(StatefulMonitor):
    """Active while a hero flag equals the wanted value, from the change to it until it changes back.

    The first update only records the flag, so joining mid-game with the flag already
    in the wanted state does not fire.
    """

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
        self._field, self._value = self._settings(rule)
        self._prev: bool | None = None

    def _settings(self, rule: Rule) -> tuple[str, bool]:
        """The hero flag to watch and the value that counts as 'in state'."""
        cfg = cast("HeroBoolMonitorConfig", rule.monitor)
        return cfg.field, cfg.value

    def evaluate(self, snap: StateSnapshot) -> None:
        hero = snap.hero
        if hero is None:
            return
        current = getattr(hero, self._field)
        if current is None:
            return
        if current == self._value:
            if self._prev is not None and self._prev != current:
                self._fire()
        else:
            self._end()
        self._prev = current

    def clear(self) -> None:
        super().clear()
        self._prev = None


class HeroAliveMonitor(HeroBoolMonitor):
    """HERO_KILLED is active while the hero is dead, HERO_RESPAWNED while alive."""

    def _settings(self, rule: Rule) -> tuple[str, bool]:
        return "alive", rule.monitor.event == "HERO_RESPAWNED"
