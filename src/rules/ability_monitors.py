from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.rules.monitor_base import StateSnapshot, TargetedStatefulMonitor
from src.rules.monitor_config import MonitorConfig, MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus


class AbilityMonitorConfig(MonitorConfig):
    type: Literal[MonitorType.ABILITY]
    target: str  # internal ability name, e.g. "spectre_spectral_dagger"
    event: Literal["COOLDOWN_STARTED"]

    def _create(self, bus: EventBus, key: str) -> TargetedStatefulMonitor:
        return ABILITY_MONITOR_REGISTRY[self.event](self.target, key, bus)


class AbilityCooldownStartedMonitor(TargetedStatefulMonitor):
    """Active while the target ability is on cooldown, from the 0 to > 0 transition.

    Only tracks learned abilities (level > 0). max_cooldown is not used because
    the game reports it unreliably. Picking an ability that actually has a
    cooldown is the rule author's responsibility.
    """

    def __init__(self, target: str, event_key: str, bus: EventBus) -> None:
        super().__init__(target, event_key, bus)
        self._prev_cooldown: int | None = None
        self._slot_id: str | None = None
        self._transformed = False

    def evaluate(self, snap: StateSnapshot) -> None:
        abilities = snap.abilities
        if abilities is None:
            return
        ability = abilities.find(self._target)
        if ability is not None:
            self._slot_id = ability.slot_id
        elif self._slot_id is not None:
            # Some abilities transform in place when used (Centaur's Work Horse
            # becomes centaur_mount, then reverts): the slot stays, the name
            # changes. Losing the name from a slot while it was ready counts as
            # the cooldown starting; the later revert must not fire again.
            occupant = abilities.slots.get(self._slot_id)
            if occupant is not None and occupant.level > 0:
                if self._prev_cooldown == 0 and not self._transformed:
                    self._transformed = True
                    self._fire()
                return
        if ability is None or ability.level == 0:
            self._prev_cooldown = None
            self._transformed = False
            self._end()
            return
        cooldown = ability.cooldown
        if self._prev_cooldown == 0 and cooldown > 0 and not self._transformed:
            self._fire()
        elif cooldown == 0:
            self._end()
        if cooldown == 0 or self._transformed:
            self._transformed = False
        self._prev_cooldown = cooldown

    def clear(self) -> None:
        super().clear()
        self._prev_cooldown = None
        self._slot_id = None
        self._transformed = False


# Registry: event name → monitor class
ABILITY_MONITOR_REGISTRY: dict[str, type[TargetedStatefulMonitor]] = {
    "COOLDOWN_STARTED": AbilityCooldownStartedMonitor,
}
