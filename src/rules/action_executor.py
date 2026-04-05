from __future__ import annotations

from src.rules.config import AnyAction, LightAction, PlaySoundAction
from src.sound import SoundManager


class ActionExecutor:
    """Dispatches typed Action models to the appropriate subsystems.

    Params are validated at config load — no validation here.
    """

    def __init__(self, sound: SoundManager) -> None:
        self._sound = sound

    async def execute(self, actions: list[AnyAction]) -> None:
        for action in actions:
            if isinstance(action, PlaySoundAction):
                await self._sound.play(action.file)
            elif isinstance(action, LightAction):
                print(f"[light] rgb({action.r}, {action.g}, {action.b})")
