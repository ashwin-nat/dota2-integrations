from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Coroutine, Iterable
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar

from src.rules.bus import Event
from src.rules.config import ActionType, BaseAction
from src.rules.monitor_config import MonitorType


A = TypeVar("A", bound=BaseAction)


@dataclass(frozen=True)
class ActionBinding(Generic[A]):
    """An enabled action plus the details of the rule it came from."""
    rule_id: str
    monitor_type: MonitorType
    event_name: str
    action: A


def describe(binding: ActionBinding[Any], event: Event) -> str:
    """Log context for an action firing: the owning rule plus the event times."""
    return (
        f"rule={binding.rule_id!r} monitor={binding.monitor_type} event={binding.event_name} "
        f"game_time={event.game_time} clock_time={event.clock_time}"
    )


class ActionExecutor(ABC, Generic[A]):
    """Runs one action type. Subscribes to the event keys its bindings were registered under."""

    action_type: ClassVar[ActionType]

    def __init__(self) -> None:
        self._bindings: dict[str, list[ActionBinding[A]]] = {}

    def register(self, key: str, binding: ActionBinding[A]) -> None:
        """Startup only."""
        self._bindings.setdefault(key, []).append(binding)

    def keys(self) -> Iterable[str]:
        return self._bindings.keys()

    @abstractmethod
    def on_event(self, event: Event) -> None:
        """Fast, never blocks."""

    def workers(self) -> dict[str, Coroutine[Any, Any, None]]:
        """Background coroutines to run as tasks; most executors have none."""
        return {}
