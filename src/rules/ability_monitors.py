from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.state.abilities import Abilities, Ability, ChargeAbility
from src.rules.monitor_base import StateSnapshot, TargetedMonitorConfig, TargetedStatefulMonitor
from src.rules.monitor_config import MonitorType

if TYPE_CHECKING:
    from src.rules.bus import EventBus
    from src.rules.config import Rule


class AbilityMonitorConfig(TargetedMonitorConfig):
    """Ability events. Abilities with their own class for an event (Charge of Darkness) set `for_target` on it."""
    type: Literal[MonitorType.ABILITY]
    target: str  # internal ability name, e.g. "spectre_spectral_dagger"
    event: Literal["COOLDOWN_STARTED"]


class AbilityCooldownStartedMonitor(TargetedStatefulMonitor):
    """Active while the target ability is on cooldown, from the 0 to > 0 transition.

    Only tracks learned abilities (level > 0). max_cooldown is not used because
    the game reports it unreliably. Picking an ability that actually has a
    cooldown is the rule author's responsibility.
    """
    for_type = MonitorType.ABILITY
    for_event = "COOLDOWN_STARTED"

    def __init__(self, rule: Rule, bus: EventBus) -> None:
        super().__init__(rule, bus)
        self._prev_cooldown: int | None = None
        self._prev_charges: int | None = None
        self._slot_id: str | None = None
        self._transformed = False
        self._prev_names: frozenset[str] = frozenset()

    def evaluate(self, snap: StateSnapshot) -> None:
        abilities = snap.abilities
        if abilities is None:
            return
        names = frozenset(a.name for a in abilities)
        ability = abilities.find(self._target)
        if ability is not None:
            self._slot_id = ability.slot_id
        elif self._slot_id is not None and self._handle_transform(abilities, names):
            self._prev_names = names
            return
        if ability is None or ability.level == 0:
            self._reset_tracking()
            self._end()
        elif isinstance(ability, ChargeAbility):
            self._evaluate_charges(ability)
        else:
            self._evaluate_cooldown(ability)
        self._prev_names = names

    def _handle_transform(self, abilities: Abilities, names: frozenset[str]) -> bool:
        """The target's name is gone from every slot: was it an in-place transform?

        Some abilities transform in place when used (Centaur's Work Horse
        becomes centaur_mount, then reverts): the slot stays, the name
        changes. Losing the name from a slot while it was ready counts as
        the cooldown starting; the later revert must not fire again.
        A real transform puts a name in the slot that was not in any slot
        last frame. Invoker's rolling eviction instead shifts an existing
        spell into the slot, which is not a cast.
        TODO: an ability that transforms into a name already sitting in
        another slot would be read as an eviction and not fire. No known
        case; check whether any hero does this.

        Returns True when the frame was a transform and needs no further handling.
        """
        occupant = abilities.at(self._slot_id)
        if not (
            occupant is not None
            and occupant.level > 0
            and occupant.name not in self._prev_names
            # Kez's stance switch renames several slots at once.
            and len(names - self._prev_names) == 1
        ):
            return False
        if self._prev_cooldown == 0 and not self._transformed:
            self._transformed = True
            self._fire()
        return True

    def _evaluate_charges(self, ability: ChargeAbility) -> None:
        """Charge shape: `cooldown` doesn't track it, a cast is a charge being
        spent. Active while a charge is recharging."""
        if self._prev_charges is not None and ability.charges < self._prev_charges:
            self._end()
            self._fire()
        elif ability.charge_cooldown == 0:
            self._end()
        self._prev_charges = ability.charges

    def _evaluate_cooldown(self, ability: Ability) -> None:
        cooldown = ability.cooldown
        if (
            self._prev_cooldown is not None
            and self._is_cast(self._prev_cooldown, cooldown)
            and not self._transformed
        ):
            # A rise means a cast. Frames arrive ~1 s apart, so a short cooldown
            # recast the moment it comes up can jump 1 -> 3 without a 0 frame.
            self._end()
            self._fire()
        elif cooldown == 0:
            self._end()
        if cooldown == 0 or self._transformed:
            self._transformed = False
        self._prev_cooldown = cooldown

    def _is_cast(self, prev_cooldown: int, cooldown: int) -> bool:
        """Did the cooldown change between two frames mean the ability was cast?"""
        return cooldown > prev_cooldown

    def _reset_tracking(self) -> None:
        self._prev_cooldown = None
        self._prev_charges = None
        self._transformed = False

    def clear(self) -> None:
        super().clear()
        self._prev_cooldown = None
        self._prev_charges = None
        self._slot_id = None
        self._transformed = False
        self._prev_names = frozenset()


class ChargeOfDarknessCooldownStartedMonitor(AbilityCooldownStartedMonitor):
    """Spirit Breaker's Charge of Darkness: fire once, when it is cast.

    Why its own class: the game restarts the cooldown when the hero arrives,
    so the generic monitor is fired twice per long charge. Details:

    The game starts the cooldown when you cast it, and then starts it again
    when Spirit Breaker reaches the target (16 -> 22 in the long charge in
    recordings/charge_trigger_twice_bug.jsonl). The ability itself stays in its
    slot under the same name, so the transform handling never sees it. To the
    generic monitor that second jump looks like another cast, but nothing was
    cast: the hero just arrived. So here only a jump from "ready" (cooldown 0)
    counts as a cast. (On a short charge the second start gives the same number
    as the first, so it never looked like a jump in the first place.)
    """
    for_target = ("spirit_breaker_charge_of_darkness",)

    def _is_cast(self, prev_cooldown: int, cooldown: int) -> bool:
        return prev_cooldown == 0 and cooldown > 0
