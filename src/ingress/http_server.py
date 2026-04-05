import asyncio

from aiohttp import web


async def handle_gsi(queue: asyncio.Queue, request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    queue.put_nowait(data)

    return web.Response(text="OK")


async def serve(queue: asyncio.Queue) -> None:
    app = web.Application()

    async def _handle(request: web.Request) -> web.Response:
        return await handle_gsi(queue, request)

    app.router.add_post("/", _handle)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", 6969)
    await site.start()

    print("Listening on http://127.0.0.1:6969")

    try:
        await asyncio.get_running_loop().create_future()  # wait forever
    finally:
        await runner.cleanup()
