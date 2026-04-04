import asyncio

from src.events import EventBus, EventCode
from src.ingress.http_server import serve
from src.monitors.midas_listener import register_midas_listeners
from src.state.store import GameState


async def main() -> None:
    bus = EventBus()
    state = GameState(bus)

    @bus.on(EventCode.INCOMING_DATA)
    async def ingest(data: dict) -> None:
        await state.set(data)

    register_midas_listeners(bus)

    tasks = [
        asyncio.create_task(bus.process_forever()),
        asyncio.create_task(serve(bus)),
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
