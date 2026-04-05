from src.lighting.controller import LightingController
from src.lighting.drivers.tapo import TapoLightingDriver


def create_lighting_controller(vendor: str, config: dict, enabled: bool) -> LightingController:
    # TODO: use vendor to select the appropriate driver once more vendors are supported
    return TapoLightingDriver(config, enabled=enabled)


def get_empty_lighting_config(vendor: str) -> dict:
    # TODO: use vendor to select the appropriate driver once more vendors are supported
    return TapoLightingDriver.get_empty_config()
