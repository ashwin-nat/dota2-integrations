import asyncio
import colorsys
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import tinytuya

from src.lighting.controller import HSV, LightingController


class TuyaLightingDriver(LightingController):
    def __init__(self, config: dict, enabled: bool) -> None:
        super().__init__(enabled)
        self._device_id: str = config["device_id"]
        self._ip: str = config["ip_address"]
        self._local_key: str = config["local_key"]
        self._version: float = float(config.get("version", 3.3))
        self._device: tinytuya.BulbDevice | None = None
        # Single-thread executor: tinytuya's persistent socket is not thread-safe
        # across multiple threads; pinning all calls to one thread avoids err 901.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tuya")

    @staticmethod
    def get_empty_config() -> dict:
        return {
            "device_id": "",
            "ip_address": "",
            "local_key": "",
            "version": 3.3,
        }

    async def setup(self) -> None:
        if not self._enabled:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._connect)

    def _connect(self) -> None:
        d = tinytuya.BulbDevice(
            dev_id=self._device_id,
            address=self._ip,
            local_key=self._local_key,
            version=self._version,
        )
        d.set_socketPersistent(True)
        status = d.status()
        if "Error" in status:
            raise RuntimeError(
                f"Tuya setup failed: {status['Error']} (err {status.get('Err')}). "
                "Check device_id, local_key, and version in lighting_config_tuya.json."
            )
        self._device = d

    async def set_colour(self, hsv: HSV) -> None:
        if not self._enabled or self._device is None:
            return
        # tinytuya set_colour takes RGB 0-255; convert from HSV (s/v: 0-100)
        h, s, v = hsv.hue / 360, hsv.saturation / 100, hsv.value / 100
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor,
            partial(self._device.set_colour, round(r * 255), round(g * 255), round(b * 255)),
        )

    async def get_hsv(self) -> HSV | None:
        if not self._enabled or self._device is None:
            return None
        loop = asyncio.get_running_loop()
        status = await loop.run_in_executor(self._executor, self._device.status)
        if "Error" in status or "dps" not in status:
            return None
        # DPS 24 is a 12-char hex string encoding HSV as hhhh ssss vvvv (each 0-1000 except h 0-360)
        raw = status["dps"].get("24")
        if not isinstance(raw, str) or len(raw) != 12:
            return None
        h = int(raw[0:4], 16)
        s = int(raw[4:8], 16)
        v = int(raw[8:12], 16)
        return HSV(hue=h, saturation=round(s / 10), value=round(v / 10))
