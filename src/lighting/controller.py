import colorsys
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class HSV:
    hue: int
    saturation: int
    value: int


class LightingController(ABC):
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    @staticmethod
    @abstractmethod
    def get_empty_config() -> dict: ...

    @abstractmethod
    async def setup(self) -> None: ...

    @abstractmethod
    async def set_colour(self, hsv: HSV) -> None: ...

    @abstractmethod
    async def get_hsv(self) -> HSV | None: ...

    def rgb_to_hsv(self, r: int, g: int, b: int) -> HSV:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return HSV(round(h * 360), round(s * 100), round(v * 100))

    async def set_colour_rgb(self, r: int, g: int, b: int) -> None:
        await self.set_colour(self.rgb_to_hsv(r, g, b))
