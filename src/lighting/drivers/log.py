import logging

from src.lighting.controller import HSV, LightingController

logger = logging.getLogger(__name__)


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
        logger.info("[log-light] setup")

    async def set_colour(self, hsv: HSV) -> None:
        if not self._enabled:
            return
        logger.info(f"[log-light] set_colour h={hsv.hue} s={hsv.saturation} v={hsv.value}")
        self._hsv = hsv

    async def get_hsv(self) -> HSV | None:
        if not self._enabled:
            return None
        logger.info(f"[log-light] get_hsv -> {self._hsv}")
        return self._hsv
