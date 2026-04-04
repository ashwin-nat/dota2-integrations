import asyncio

from src.events import EventBus
from src.ingress.http_server import serve
from src.state.store import GameState


async def main() -> None:
    bus = EventBus()
    state = GameState(bus)

    tasks = [
        asyncio.create_task(serve(state)),
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
