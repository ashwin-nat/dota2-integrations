import asyncio
from functools import partial

from aiohttp import web

from src.events import EventBus, EventCode


async def handle_gsi(bus: EventBus, request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    bus.emit(EventCode.INCOMING_DATA, data=data)

    return web.Response(text="OK")


async def serve(bus: EventBus) -> None:
    app = web.Application()
    app.router.add_post("/", partial(handle_gsi, bus))

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", 6969)
    await site.start()

    print("Listening on http://127.0.0.1:6969")

    try:
        await asyncio.get_running_loop().create_future()  # wait forever
    finally:
        await runner.cleanup()
