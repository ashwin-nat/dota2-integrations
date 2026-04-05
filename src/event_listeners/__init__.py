from src.events import EventBus
from src.lighting.controller import LightingController
from src.sound import SoundManager

__all__ = ["register_listeners"]


def register_listeners(bus: EventBus, lighting: LightingController, sound: SoundManager) -> None:
    pass
