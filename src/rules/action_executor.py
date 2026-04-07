from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from src.lighting.controller import LightingController
from src.rules.config import (
    ActionType,
    AnyAction,
    LightAction,
    LoggerAction,
    MapColours,
    PlaySoundAction,
)
from src.sound import SoundManager

if TYPE_CHECKING:
    from src.state.map import MapState


class ActionExecutor:
    """Dispatches typed Action models to the appropriate subsystems.

    Params are validated at config load — no validation here.
    """

    def __init__(
        self,
        sound: SoundManager,
        lighting: LightingController,
        map_colours: MapColours | None = None,
        get_map: Callable[[], MapState | None] | None = None,
    ) -> None:
        self._sound = sound
        self._lighting = lighting
        self._map_colours = map_colours
        self._get_map = get_map

        self._dispatch = {
            ActionType.PLAY_SOUND:  self._execute_play_sound,
            ActionType.LIGHT:       self._execute_light,
            ActionType.RESET_LIGHT: self._execute_reset_light,
            ActionType.LOGGER:      self._execute_logger,
        }

    async def execute(self, actions: list[AnyAction]) -> None:
        for action in actions:
            await self._dispatch[action.type](action)

    async def _execute_play_sound(self, action: PlaySoundAction) -> None:
        await self._sound.play(action.file, volume=action.volume / 100)

    async def _execute_light(self, action: LightAction) -> None:
        await self._lighting.set_colour_rgb(action.r, action.g, action.b)

    async def _execute_reset_light(self, _action: AnyAction) -> None:
        if self._map_colours is None or self._get_map is None:
            return
        map_state = self._get_map()
        if map_state is None:
            return
        colour = self._map_colours.day if map_state.daytime else self._map_colours.night
        await self._lighting.set_colour_rgb(colour.r, colour.g, colour.b)

    async def _execute_logger(self, action: LoggerAction) -> None:
        print(f"[logger] {action.message}")
