from src.lighting.controller import HSV, LightingController


class LogLightingDriver(LightingController):
    """No-op driver that only logs calls. Useful for exercising rules without hardware."""

    def __init__(self, config: dict, enabled: bool) -> None:
        super().__init__(enabled)
        self._hsv: HSV | None = None

    @staticmethod
    def get_empty_config() -> dict:
        return {}

    async def setup(self) -> None:
        if not self._enabled:
            return
        print("[log-light] setup")

    async def set_colour(self, hsv: HSV) -> None:
        if not self._enabled:
            return
        print(f"[log-light] set_colour h={hsv.hue} s={hsv.saturation} v={hsv.value}")
        self._hsv = hsv

    async def get_hsv(self) -> HSV | None:
        if not self._enabled:
            return None
        print(f"[log-light] get_hsv -> {self._hsv}")
        return self._hsv
