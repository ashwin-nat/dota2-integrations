from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.state.store import GameState


@runtime_checkable
class Monitor(Protocol):
    async def update(self, state: GameState) -> None: ...
    def clear(self) -> None: ...
