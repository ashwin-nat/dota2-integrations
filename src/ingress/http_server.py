import asyncio
from functools import partial

from aiohttp import web

from src.state.store import GameState


async def handle_gsi(state: GameState, request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    await state.set(data)

    return web.Response(text="OK")


async def serve(state: GameState) -> None:
    app = web.Application()
    app.router.add_post("/", partial(handle_gsi, state))

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", 6969)
    await site.start()

    print("Listening on http://127.0.0.1:6969")

    try:
        await asyncio.get_running_loop().create_future()  # wait forever
    finally:
        await runner.cleanup()
