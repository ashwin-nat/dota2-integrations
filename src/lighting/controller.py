from dataclasses import dataclass

from kasa import Discover, Device


@dataclass
class HSV:
    hue: int
    saturation: int
    value: int


class LightingController:
    def __init__(self, ip: str, username: str, password: str, enabled: bool) -> None:
        self._ip = ip
        self._username = username
        self._password = password
        self._enabled = enabled
        self._device: Device | None = None

    async def connect(self) -> None:
        if not self._enabled:
            return
        self._device = await Discover.discover_single(
            self._ip, username=self._username, password=self._password
        )
        await self._device.update()

    async def set_colour(self, hsv: HSV) -> None:
        if not self._enabled or self._device is None:
            return
        await self._device.set_hsv(hsv.hue, hsv.saturation, hsv.value)

    async def get_hsv(self) -> HSV | None:
        if not self._enabled or self._device is None:
            return None

        await self._device.update()
        hsv = self._device.state_information.get("HSV")
        if hsv is None:
            return None
        return HSV(hue=hsv.hue, saturation=hsv.saturation, value=hsv.value)
