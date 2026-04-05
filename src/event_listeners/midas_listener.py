from __future__ import annotations

from src.events import EventBus, EventCode
from src.state.items import MultiChargeItem
from src.sound import SoundManager


def register_midas_listeners(bus: EventBus, sound: SoundManager) -> None:
    @bus.on(EventCode.MIDAS_PURCHASED)
    async def on_purchased(item: MultiChargeItem, **_) -> None:
        print(f"Midas purchased in slot {item.slot_id}!")
        await sound.play("media/rararara.mp3")

    @bus.on(EventCode.MIDAS_CHARGED)
    async def on_charged(item: MultiChargeItem, **_) -> None:
        print(f"Midas charged in slot {item.slot_id}!")

    @bus.on(EventCode.MIDAS_OVERCHARGED)
    async def on_overcharged(item: MultiChargeItem, **_) -> None:
        print(f"Midas overcharged in slot {item.slot_id}!")
