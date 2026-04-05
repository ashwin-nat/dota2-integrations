from src.event_listeners.day_night_listener import register_day_night_listeners
from src.event_listeners.midas_listener import register_midas_listeners
from src.events import EventBus
from src.lighting.controller import LightingController
from src.sound import SoundManager

__all__ = ["register_listeners"]


def register_listeners(bus: EventBus, lighting: LightingController, sound: SoundManager) -> None:
    register_midas_listeners(bus, sound)
    register_day_night_listeners(bus, lighting)
