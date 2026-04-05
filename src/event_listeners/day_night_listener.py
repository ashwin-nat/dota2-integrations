from __future__ import annotations

from src.events import EventBus, EventCode
from src.lighting.controller import HSV, LightingController
from src.state.map import MapState


def register_day_night_listeners(bus: EventBus, lighting: LightingController) -> None:
    @bus.on(EventCode.DAYTIME_STARTED)
    async def on_daytime(**_) -> None:
        print("Daytime started")
        await lighting.set_colour(HSV(50, 15, 100))

    @bus.on(EventCode.NIGHTTIME_STARTED)
    async def on_nighttime(ns_night: bool = False, **_) -> None:
        suffix = " (Nightstalker night)" if ns_night else ""
        print(f"Nighttime started{suffix}")
        await lighting.set_colour(HSV(240, 100, 100))
