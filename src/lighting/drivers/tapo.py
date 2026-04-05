from kasa import Discover, Device

from src.lighting.controller import HSV, LightingController


class TapoLightingDriver(LightingController):
    def __init__(self, config: dict, enabled: bool) -> None:
        super().__init__(enabled)
        self._ip: str = config["ipaddr"]
        self._username: str = config["username"]
        self._password: str = config["password"]
        self._device: Device | None = None

    @staticmethod
    def get_empty_config() -> dict:
        return {
            "ipaddr": "",
            "username": "",
            "password": "",
        }

    async def setup(self) -> None:
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
