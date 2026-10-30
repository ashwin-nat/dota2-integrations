from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable

from aiohttp import web
from pydantic import ValidationError

from src.config_ui.catalog import load_catalog
from src.config_ui.files import AUDIO_EXTENSIONS, MEDIA_DIR, safe_filename
from src.config_ui.soundboard import setup_soundboard
from src.rules.config import RulesConfig
from src.sound import SoundManager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# Called with the validated config after it has been written to disk.
# Returns True when a change needs an app restart to take effect.
ReloadFn = Callable[[RulesConfig], bool]


def setup_config_ui(
    app: web.Application,
    rules_path: Path,
    reload: ReloadFn,
    sound: SoundManager,
    shutdown: Callable[[], None] | None = None,
) -> None:
    """Mount the rules editor at /ui and its JSON API at /api on the GSI server's app."""

    async def index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def get_config(_: web.Request) -> web.Response:
        return web.json_response(json.loads(rules_path.read_text()))

    async def put_config(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "errors": [{"loc": [], "msg": "Invalid JSON"}]}, status=400)
        try:
            config = RulesConfig.model_validate(data)
        except ValidationError as e:
            errors = [{"loc": list(err["loc"]), "msg": err["msg"].removeprefix("Value error, ")} for err in e.errors()]
            return web.json_response({"ok": False, "errors": errors}, status=422)
        rules_path.write_text(json.dumps(config.model_dump(mode="json"), indent=4))
        restart_required = reload(config)
        logger.info(f"Rules updated from editor: {len(config.rules)} rules")
        return web.json_response({"ok": True, "restart_required": restart_required})

    async def list_media(_: web.Request) -> web.Response:
        files = sorted(
            (p for p in MEDIA_DIR.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS),
            key=lambda p: p.name.lower(),
        ) if MEDIA_DIR.is_dir() else []
        return web.json_response([{"file": f"media/{p.name}", "name": p.name, "size": p.stat().st_size} for p in files])

    async def upload_media(request: web.Request) -> web.Response:
        reader = await request.multipart()
        field = await reader.next()
        if field is None or not getattr(field, "filename", None):
            return web.json_response({"ok": False, "error": "No file uploaded"}, status=400)
        # ?name= saves the clip under the file name a rule already expects
        name = safe_filename(request.query.get("name") or field.filename)  # type: ignore[union-attr]
        if Path(name).suffix not in AUDIO_EXTENSIONS:
            return web.json_response({"ok": False, "error": "Only .mp3, .wav and .ogg files are supported"}, status=400)
        MEDIA_DIR.mkdir(exist_ok=True)
        dest = MEDIA_DIR / name
        size = 0
        with dest.open("wb") as f:
            while chunk := await field.read_chunk():  # type: ignore[union-attr]
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    f.close()
                    dest.unlink()
                    return web.json_response({"ok": False, "error": "File is larger than 20 MB"}, status=400)
                f.write(chunk)
        logger.info(f"Uploaded sound {dest} ({size} bytes)")
        return web.json_response({"ok": True, "file": f"media/{name}", "name": name, "size": size})

    async def play(request: web.Request) -> web.Response:
        body = await request.json()
        path = Path(body.get("file", ""))
        if path.parent != MEDIA_DIR or not path.is_file():
            return web.json_response({"ok": False, "error": "Unknown sound file"}, status=400)
        volume = max(0, min(100, int(body.get("volume", 100))))
        await sound.play(str(path), volume=volume / 100)
        return web.json_response({"ok": True})

    async def catalog(_: web.Request) -> web.Response:
        data = await load_catalog()
        if data is None:
            return web.json_response({"heroes": [], "items": [], "offline": True})
        return web.json_response(data)

    async def info(_: web.Request) -> web.Response:
        return web.json_response({"data_dir": str(Path.cwd()), "can_shutdown": shutdown is not None})

    async def power_off(_: web.Request) -> web.Response:
        if shutdown is None:
            return web.json_response({"ok": False, "error": "Shutdown isn't available"}, status=400)
        logger.info("Shutdown requested from the editor")
        # Give the response time to reach the browser before the server stops
        asyncio.get_running_loop().call_later(0.3, shutdown)
        return web.json_response({"ok": True})

    async def redirect_ui(_: web.Request) -> web.Response:
        raise web.HTTPFound("/ui")

    async def no_cache_ui(request: web.Request, response: web.StreamResponse) -> None:
        # Always revalidate the editor's files so an app update shows up on reload
        if request.path.startswith("/ui"):
            response.headers["Cache-Control"] = "no-cache"

    app.on_response_prepare.append(no_cache_ui)
    app.router.add_get("/", redirect_ui)
    app.router.add_get("/ui", index)
    app.router.add_static("/ui/static", STATIC_DIR)
    app.router.add_get("/api/config", get_config)
    app.router.add_put("/api/config", put_config)
    app.router.add_get("/api/media", list_media)
    app.router.add_post("/api/media", upload_media)
    app.router.add_post("/api/play", play)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_get("/api/info", info)
    app.router.add_post("/api/shutdown", power_off)
    setup_soundboard(app, sound, rules_path, reload)
    # A fresh install (e.g. the macOS app's Application Support dir) has no media/ yet
    MEDIA_DIR.mkdir(exist_ok=True)
    app.router.add_static("/media", MEDIA_DIR)
