import asyncio
import logging
import os
from typing import Callable

from aiohttp import web

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("GSI_PORT", "6969"))


async def handle_gsi(queue: asyncio.Queue, request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    queue.put_nowait(data)

    return web.Response(text="OK")


async def serve(queue: asyncio.Queue, setup_app: Callable[[web.Application], None] | None = None) -> None:
    app = web.Application(client_max_size=25 * 1024 * 1024)

    async def _handle(request: web.Request) -> web.Response:
        return await handle_gsi(queue, request)

    app.router.add_post("/", _handle)
    if setup_app is not None:
        setup_app(app)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()

    logger.info(f"Listening on http://127.0.0.1:{PORT} (rules editor: http://127.0.0.1:{PORT}/ui)")

    try:
        await asyncio.get_running_loop().create_future()  # wait forever
    finally:
        await runner.cleanup()
