import asyncio
from functools import partial

from aiohttp import web

from src.ingress.http_handler import handle_gsi
from src.state.store import GameState


async def run_server(state: GameState) -> web.AppRunner:
    app = web.Application()
    app.router.add_post("/", partial(handle_gsi, state))

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", 6969)
    await site.start()

    print("Listening on http://127.0.0.1:6969")

    return runner


async def main_loop() -> None:
    state = GameState()

    runner = await run_server(state)

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
