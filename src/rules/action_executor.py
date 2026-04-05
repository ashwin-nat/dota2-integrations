from __future__ import annotations

from src.lighting.controller import LightingController
from src.rules.config import AnyAction, LightAction, LoggerAction, PlaySoundAction
from src.sound import SoundManager


class ActionExecutor:
    """Dispatches typed Action models to the appropriate subsystems.

    Params are validated at config load — no validation here.
    """

    def __init__(self, sound: SoundManager, lighting: LightingController) -> None:
        self._sound = sound
        self._lighting = lighting

    async def execute(self, actions: list[AnyAction]) -> None:
        for action in actions:
            if isinstance(action, PlaySoundAction):
                await self._sound.play(action.file)
            elif isinstance(action, LightAction):
                await self._lighting.set_colour_rgb(action.r, action.g, action.b)
            elif isinstance(action, LoggerAction):
                print(f"[logger] {action.message}")
