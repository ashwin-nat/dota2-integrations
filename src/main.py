import asyncio
import json
import sys
from pathlib import Path

LIGHTING_ENABLED = True

LIGHTING_CONFIG_PATH = Path("lighting_config.json")
LIGHTING_CONFIG_DEFAULTS = {
    "ipaddr": "",
    "username": "",
    "password": "",
}

from src.event_listeners import register_listeners
from src.events import EventBus, EventCode
from src.ingress.http_server import serve
from src.lighting.controller import LightingController
from src.sound import SoundManager
from src.state.store import GameState


def load_lighting_config() -> dict:
    if not LIGHTING_CONFIG_PATH.exists():
        LIGHTING_CONFIG_PATH.write_text(
            json.dumps(LIGHTING_CONFIG_DEFAULTS, indent=4)
        )
        print(
            f"Lighting config created at '{LIGHTING_CONFIG_PATH}'. "
            "Please fill in ipaddr, username, and password, then restart."
        )
        sys.exit(0)

    return json.loads(LIGHTING_CONFIG_PATH.read_text())


def _exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    exc = context.get("exception")
    msg = context.get("message", "")
    # Suppress debugger-induced noise: pausing execution leaves the socket in a
    # state where IOCP accept() fails with WinError 64, and aiohttp's
    # _request_factory is None because the handler hasn't resumed yet.
    if isinstance(exc, OSError) and exc.winerror == 64:
        return
    if isinstance(exc, TypeError) and "'NoneType' object is not callable" in str(exc):
        return
    if "Accept failed on a socket" in msg:
        return
    loop.default_exception_handler(context)


async def main() -> None:
    asyncio.get_event_loop().set_exception_handler(_exception_handler)

    lighting_config = load_lighting_config() if LIGHTING_ENABLED else None

    lighting = LightingController(
        ip=lighting_config["ipaddr"] if lighting_config else "",
        username=lighting_config["username"] if lighting_config else "",
        password=lighting_config["password"] if lighting_config else "",
        enabled=LIGHTING_ENABLED,
    )
    await lighting.connect()

    bus = EventBus()
    state = GameState(bus)
    sound = SoundManager()

    @bus.on(EventCode.INCOMING_DATA)
    async def ingest(data: dict) -> None:
        await state.set(data)

    register_listeners(bus, lighting, sound)

    tasks = [
        asyncio.create_task(bus.process_forever()),
        asyncio.create_task(serve(bus)),
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
