from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from src.rules.monitor_config import MonitorConfig, MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.config import Rule
    from src.state.abilities import Abilities
    from src.state.hero import HeroState
    from src.state.items import Items
    from src.state.map import MapState
    from src.state.player import PlayerState


@dataclass(frozen=True)
class StateSnapshot:
    """Everything a monitor can look at, built once per update by GameState.

    A part is None when the update did not carry it; each monitor returns early
    if the part it needs is missing.
    """
    items: Items | None
    prev_items: Items | None
    abilities: Abilities | None
    hero: HeroState | None
    player: PlayerState | None
    map: MapState | None


class Monitor(ABC):
    """Watches the game snapshot and publishes events on the bus."""

    type: MonitorType  # set by MonitorConfig.build; used for logs and the startup counts
    # Also evaluated during pre-game (clock -1:30 to the horn). Only monitors that read just the map clock.
    runs_before_horn: bool = False

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        self._rule = rule
        self._event_key = rule.id  # the bus key this monitor publishes under
        self._bus = bus
        self._seen_update = False

    def run(self, snap: StateSnapshot) -> None:
        """Evaluate one update. Events published during a monitor's first update since start or
        `reset()` are marked initial: the state was unknown before, so they report what is already
        true (starting items, day/night), not something that happened. Sounds skip them."""
        self._bus.initial = not self._seen_update
        self._seen_update = True
        try:
            self.evaluate(snap)
        finally:
            self._bus.initial = False

    def reset(self) -> None:
        """Clear per-match state and forget that an update was seen (on a match change)."""
        self._seen_update = False
        self.clear()

    @abstractmethod
    def evaluate(self, snap: StateSnapshot) -> None:
        """Look at one update and emit (or retract) events."""

    @abstractmethod
    def clear(self) -> None:
        """Reset per-match state (called on a match change)."""


class StatefulMonitor(Monitor):
    """Base for monitors that signal a state that begins and later ends.

    ``_fire`` emits the event when the state begins (actions run, light
    requests are set). ``_end`` retracts the event's light requests when the
    state ends; it is a no-op unless the monitor is currently active, so it is
    safe to call on every evaluation. ``clear`` resets per-match state.
    """

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
        self._active = False

    def _fire(self) -> None:
        self._active = True
        self._bus.emit(self._event_key)

    def _end(self) -> None:
        if self._active:
            self._active = False
            self._bus.retract(self._event_key)

    def clear(self) -> None:
        self._active = False


class TargetedStatefulMonitor(StatefulMonitor):
    """A stateful monitor that watches one named target (an item or ability name).

    The target comes from the rule's monitor config (`target`). Its configs have several
    events, so every subclass says which one it handles, and the config finds it with
    `monitor_class`:

        class CooldownReadyMonitor(TargetedStatefulMonitor):
            for_type = MonitorType.ITEM
            for_event = "COOLDOWN_READY"

    `for_target` limits a class to one item or ability name (others fall back to the class
    without one). The fields are inherited, so a specialised subclass sets only what differs
    (Blink: `for_target = "item_blink"`); a subclass that changes none just shares code.
    """

    # Every subclass must set for_type and for_event (checked in __init__)
    for_type: ClassVar[MonitorType | None] = None
    for_event: ClassVar[str | None] = None
    for_target: ClassVar[str | None] = None

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        assert self.for_type is not None, f"{type(self).__name__} must set for_type"
        assert self.for_event is not None, f"{type(self).__name__} must set for_event"
        super().__init__(rule, bus)
        self._target: str = rule.monitor.target

    @classmethod
    def declared_for(cls) -> tuple[MonitorType, str, str | None]:
        """(for_type, for_event, for_target): the event and target this class handles."""
        # Every subclass today is a monitor for its own event; none exists only to share code.
        # These asserts catch a forgotten for_type / for_event, and a subclass that changes none
        # of the fields (it would claim its parent's event). If an intermediate base or a
        # code-sharing subclass is ever needed, remove them and skip such classes in monitor_class.
        assert cls.for_type is not None, f"{cls.__name__} must set for_type"
        assert cls.for_event is not None, f"{cls.__name__} must set for_event"
        key = (cls.for_type, cls.for_event, cls.for_target)
        for base in cls.__bases__:
            if issubclass(base, TargetedStatefulMonitor):
                assert (base.for_type, base.for_event, base.for_target) != key, (
                    f"{cls.__name__} sets the same for_type, for_event and for_target as {base.__name__}"
                )
        return key


def _subclasses(cls: type[TargetedStatefulMonitor]) -> set[type[TargetedStatefulMonitor]]:
    found: set[type[TargetedStatefulMonitor]] = set()
    for sub in cls.__subclasses__():
        found.add(sub)
        found |= _subclasses(sub)
    return found


def monitor_class(
    monitor_type: MonitorType, event: str, target: str | None = None
) -> type[TargetedStatefulMonitor]:
    """The monitor class declared for this event and target, else the one for the event alone."""
    by_key: dict[tuple[MonitorType, str, str | None], type[TargetedStatefulMonitor]] = {}
    for cls in _subclasses(TargetedStatefulMonitor):
        key = cls.declared_for()
        assert key not in by_key, f"{cls.__name__} and {by_key[key].__name__} both declare {key}"
        by_key[key] = cls
    found = by_key.get((monitor_type, event, target)) or by_key.get((monitor_type, event, None))
    # Config validation only lets through events listed in the config's Literal
    assert found is not None, f"no monitor class declared for {monitor_type} {event}"
    return found


class TargetedMonitorConfig(MonitorConfig):
    """Config for a type whose events each have their own TargetedStatefulMonitor subclass.

    `_create` builds the class declared for this config's type, event and target. A config
    with a fixed target (Midas, Blink) overrides `target` with a default that is not saved.
    """
    target: str
    event: str

    # Look up the classes declared for this type instead of the config's own (Blink rules use
    # the item classes); None means the config's `type`.
    uses_classes_of: ClassVar[MonitorType | None] = None

    def _create(self, bus: EventBus, rule: Rule) -> TargetedStatefulMonitor:
        return monitor_class(self.uses_classes_of or self.type, self.event, self.target)(rule, bus)
