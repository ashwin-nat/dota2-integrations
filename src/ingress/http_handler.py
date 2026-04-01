from aiohttp import web

from src.state.store import GameState


async def handle_gsi(state: GameState, request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    state.set(data)

    return web.Response(text="OK")
