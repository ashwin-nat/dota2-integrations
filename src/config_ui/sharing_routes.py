from __future__ import annotations

import asyncio
import os
import string
import sys
from pathlib import Path
from typing import Callable

from aiohttp import web

from src import sharing
from src.media import media_dir
from src.rules.config import RulesConfig


def _cloud_folders() -> list[dict]:
    """Likely sync folders on this computer, so nobody has to type a path."""
    home = Path.home()
    found: list[tuple[str, Path]] = []
    if sys.platform == "darwin":
        cloud = home / "Library" / "CloudStorage"
        if cloud.is_dir():
            for d in sorted(cloud.iterdir()):
                if d.name.startswith("GoogleDrive-"):
                    account = d.name.removeprefix("GoogleDrive-")
                    for sub in ("My Drive", "Shared drives"):
                        if (d / sub).is_dir():
                            found.append((f"Google Drive · {sub} ({account})", d / sub))
                elif d.name.startswith("OneDrive"):
                    found.append(("OneDrive", d))
                elif d.name.startswith("Dropbox"):
                    found.append(("Dropbox", d))
        icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        if icloud.is_dir():
            found.append(("iCloud Drive", icloud))
    elif sys.platform == "win32":
        for letter in string.ascii_uppercase:
            for sub in ("My Drive", "Shared drives"):
                p = Path(f"{letter}:\\") / sub
                if p.is_dir():
                    found.append((f"Google Drive · {sub} ({letter}:)", p))
        if os.environ.get("OneDrive"):
            found.append(("OneDrive", Path(os.environ["OneDrive"])))
    for label, p in (("Dropbox", home / "Dropbox"), ("Google Drive", home / "Google Drive")):
        if p.is_dir() and all(p != f for _, f in found):
            found.append((label, p))
    found.append(("Home folder", home))
    return [{"label": label, "path": str(p)} for label, p in found]


def _looks_shared(p: Path) -> bool:
    return (p / sharing.PEOPLE_DIR).is_dir()


def setup_sharing(app: web.Application, rules_path: Path, reload: Callable[[RulesConfig], bool]) -> None:
    """Mount /api/sharing: turn the shared folder on or off, follow friends, browse for the folder."""

    def state() -> dict:
        s = sharing.settings()
        folder = sharing.shared_folder()
        return {
            "enabled": folder is not None,
            "available": bool(folder and folder.is_dir()),
            "folder": s.folder,
            "name": s.name,
            "media_dir": str(media_dir().resolve()),
            "people": sharing.friends(),
        }

    def recompile() -> None:
        # The media folder or followed friends changed; rebuild the engine from disk
        reload(RulesConfig.load(rules_path))

    # Everything here touches the shared folder, which can be slow (a cloud drive fetching
    # listings) or held up by a macOS permission prompt, so it runs off the event loop and
    # never stalls in-game sounds.

    async def get_state(_: web.Request) -> web.Response:
        return web.json_response(await asyncio.to_thread(state))

    async def put_state(request: web.Request) -> web.Response:
        body = await request.json()
        try:
            result = await asyncio.to_thread(sharing.configure, body.get("folder") or None, str(body.get("name", "")), bool(body.get("create")))
        except (sharing.SharingError, OSError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        recompile()
        return web.json_response({"ok": True, **result, **await asyncio.to_thread(state)})

    async def follow(request: web.Request) -> web.Response:
        body = await request.json()
        sharing.set_following(str(body.get("name", "")), bool(body.get("follow")))
        recompile()
        return web.json_response({"ok": True, **await asyncio.to_thread(state)})

    def list_dir(path: Path) -> dict:
        dirs = sorted(
            (d for d in path.iterdir() if d.is_dir() and not d.name.startswith((".", "$"))),
            key=lambda d: d.name.lower(),
        )
        return {
            "path": str(path),
            "parent": str(path.parent) if path.parent != path else None,
            "shared": _looks_shared(path),
            "dirs": [{"name": d.name, "path": str(d), "shared": _looks_shared(d)} for d in dirs[:500]],
        }

    async def browse(request: web.Request) -> web.Response:
        raw = request.query.get("path")
        if not raw:
            suggestions = await asyncio.to_thread(_cloud_folders)
            return web.json_response({"path": None, "parent": None, "dirs": [], "suggestions": suggestions})
        path = Path(raw).expanduser()
        try:
            listing = await asyncio.wait_for(asyncio.to_thread(list_dir, path), timeout=60)
        except TimeoutError:
            return web.json_response({"ok": False, "error": (
                f"{path} is taking too long to open. If macOS asked for permission to access it, click Allow and try again."
            )}, status=504)
        except OSError as e:
            return web.json_response({"ok": False, "error": f"Can't open {path}: {e.strerror or e}"}, status=400)
        return web.json_response(listing)

    app.router.add_get("/api/sharing", get_state)
    app.router.add_put("/api/sharing", put_state)
    app.router.add_post("/api/sharing/follow", follow)
    app.router.add_get("/api/sharing/browse", browse)
