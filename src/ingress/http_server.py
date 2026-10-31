import asyncio
import logging
import os
from typing import Callable

from aiohttp import web

from src.recorder import Recorder
from src.rules.bus import RuleEventBus
from src.state.store import GameState

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("GSI_PORT", "6969"))


async def handle_gsi(queue: asyncio.Queue, request: web.Request, recorder: Recorder | None = None) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    # Real Dota never sends this; the replay tool injects it for frames annotated in a recording.
    note = data.pop("note", None)
    if note:
        logger.info(f"GSI note: {note}")

    if recorder is not None:
        recorder.record(data)
    queue.put_nowait(data)

    return web.Response(text="OK")


async def serve(
    queue: asyncio.Queue,
    setup_app: Callable[[web.Application], None] | None = None,
    on_started: Callable[[str], None] | None = None,
    recorder: Recorder | None = None,
    state: GameState | None = None,
    rule_bus: RuleEventBus | None = None,
) -> None:
    app = web.Application(client_max_size=25 * 1024 * 1024)

    async def _handle(request: web.Request) -> web.Response:
        return await handle_gsi(queue, request, recorder)

    app.router.add_post("/", _handle)
    if setup_app is not None:
        setup_app(app)

    if state is not None and rule_bus is not None:
        async def _state(request: web.Request) -> web.Response:
            # Wait until every queued payload has been processed so the dump is
            # deterministic right after a POST (the replay stepper relies on this).
            await queue.join()
            return web.json_response({
                "version": state.version(),
                "raw": state.raw,
                "fired": rule_bus.drain_fired(),
            })

        app.router.add_get("/state", _state)

    if recorder is not None:
        async def _save(request: web.Request) -> web.Response:
            path = recorder.save()
            return web.Response(text=f"Saved {len(recorder)} payloads to {path}\n")

        app.router.add_route("*", "/record/save", _save)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()

    base_url = f"http://127.0.0.1:{PORT}"
    logger.info(f"Listening on {base_url} (rules editor: {base_url}/ui)")
    if on_started is not None:
        on_started(base_url)

    try:
        await asyncio.get_running_loop().create_future()  # wait forever
    finally:
        await runner.cleanup()
