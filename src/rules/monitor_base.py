from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.rules.bus import RuleEventBus


class StatefulMonitor:
    """Base for monitors that signal a state that begins and later ends.

    ``_fire`` emits the event when the state begins (actions run, light
    requests are set). ``_end`` retracts the event's light requests when the
    state ends; it is a no-op unless the monitor is currently active, so it is
    safe to call on every evaluation. ``clear`` resets per-match state.
    """

    def __init__(self, event_key: str, bus: RuleEventBus) -> None:
        self._event_key = event_key
        self._bus = bus
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
