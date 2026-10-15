import json
import sys
from pathlib import Path

from src.lighting.controller import LightingController
from src.lighting.drivers.log import LogLightingDriver
from src.lighting.drivers.tapo import TapoLightingDriver
from src.lighting.drivers.tuya import TuyaLightingDriver
from src.rules.config import LightingVendor

_VENDOR_DRIVERS: dict[LightingVendor, type[LightingController]] = {
    LightingVendor.TAPO: TapoLightingDriver,
    LightingVendor.TUYA: TuyaLightingDriver,
    LightingVendor.LOG: LogLightingDriver,
}


def load_lighting_controller(vendor: LightingVendor, enabled: bool) -> LightingController:
    driver_cls = _VENDOR_DRIVERS[vendor]

    # Drivers with no config fields don't need a config file
    if not driver_cls.get_empty_config():
        return driver_cls({}, enabled=enabled)

    config_path = Path(f"lighting_config_{vendor}.json")

    if not config_path.exists():
        config_path.write_text(json.dumps(driver_cls.get_empty_config(), indent=4))
        print(
            f"Lighting config created at '{config_path}'. "
            "Please fill in the required fields, then restart."
        )
        sys.exit(0)

    config = json.loads(config_path.read_text())
    return driver_cls(config, enabled=enabled)
