from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from src.lighting.controller import LightingController
from src.rules.config import AnyAction, LightAction, LoggerAction, MapColours, PlaySoundAction, ResetLightAction
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

    async def execute(self, actions: list[AnyAction]) -> None:
        for action in actions:
            if isinstance(action, PlaySoundAction):
                await self._sound.play(action.file)
            elif isinstance(action, LightAction):
                await self._lighting.set_colour_rgb(action.r, action.g, action.b)
            elif isinstance(action, ResetLightAction):
                await self._execute_reset_light()
            elif isinstance(action, LoggerAction):
                print(f"[logger] {action.message}")

    async def _execute_reset_light(self) -> None:
        if self._map_colours is None or self._get_map is None:
            return
        map_state = self._get_map()
        if map_state is None:
            return
        colour = self._map_colours.day if map_state.daytime else self._map_colours.night
        await self._lighting.set_colour_rgb(colour.r, colour.g, colour.b)
