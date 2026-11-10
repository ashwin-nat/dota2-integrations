from __future__ import annotations

import asyncio
import os
import string
import sys
from pathlib import Path
from typing import Callable

from aiohttp import web

from src import drive, packs, sharing, shortcuts
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
    routes = web.RouteTableDef()

    def sharing_state() -> dict:
        s = sharing.settings()
        folder = sharing.shared_folder()
        return {
            "enabled": folder is not None,
            "available": bool(folder and folder.is_dir()),
            "folder": s.folder,
            "name": s.name,
            "media_dir": str(media_dir().resolve()),
            "people": sharing.friends(),
            "packs": [
                {
                    "key": f"{sharing.PACK_PREFIX}{p['id']}", "kind": "pack", "id": p["id"], "name": p["name"],
                    "source": p.get("source"), "updated": p.get("updated"), "imported": p.get("imported"),
                    "rules": p["rules"], "soundboard": p["soundboard"],
                    "following": f"{sharing.PACK_PREFIX}{p['id']}" in s.following,
                }
                for p in packs.list_packs()
            ],
        }

    def recompile() -> None:
        # The media folder or followed friends changed; rebuild the engine from disk
        reload(RulesConfig.load(rules_path, allow_missing_sounds=True))

    # Everything here touches the shared folder, which can be slow (a cloud drive fetching
    # listings) or held up by a macOS permission prompt, so it runs off the event loop and
    # never stalls in-game sounds.

    @routes.get("/api/sharing")
    async def get_state(_: web.Request) -> web.Response:
        return web.json_response(await asyncio.to_thread(sharing_state))

    @routes.put("/api/sharing")
    async def put_state(request: web.Request) -> web.Response:
        body = await request.json()
        try:
            result = await asyncio.to_thread(sharing.configure, body.get("folder") or None, str(body.get("name", "")), bool(body.get("create")))
        except (sharing.SharingError, OSError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        recompile()
        return web.json_response({"ok": True, **result, **await asyncio.to_thread(sharing_state)})

    @routes.post("/api/sharing/follow")
    async def follow(request: web.Request) -> web.Response:
        body = await request.json()
        sharing.set_following(str(body.get("name", "")), bool(body.get("follow")))
        recompile()
        return web.json_response({"ok": True, **await asyncio.to_thread(sharing_state)})

    def list_dir(path: Path) -> dict:
        dirs = sorted(
            (d for d in path.iterdir() if d.is_dir() and not d.name.startswith((".", "$"))),
            key=lambda d: d.name.lower(),
        )
        entries = [(d.name, d) for d in dirs]
        # Drive shows a shared folder added to My Drive as a .lnk; list it as the folder it points to
        for lnk in path.glob("*.lnk"):
            if (target := shortcuts.read_lnk(lnk)) and target.is_dir():
                entries.append((lnk.stem, target))
        entries.sort(key=lambda e: e[0].lower())
        return {
            "path": str(path),
            "parent": str(path.parent) if path.parent != path else None,
            "shared": _looks_shared(path),
            "dirs": [{"name": n, "path": str(d), "shared": _looks_shared(d)} for n, d in entries[:500]],
        }

    @routes.get("/api/sharing/browse")
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

    @routes.post("/api/sharing/join")
    async def join(request: web.Request) -> web.Response:
        """Join the shared folder behind a Drive folder link, once Drive for desktop has it."""
        body = await request.json()
        folder_id = drive.folder_id_from_link(str(body.get("link", "")))
        if not folder_id:
            return web.json_response({"ok": False, "error": "That isn't a Google Drive folder link"}, status=400)
        base = {"ok": True, "open_url": drive.folder_link(folder_id), "download_url": drive.DOWNLOAD_URL}
        try:
            roots = await asyncio.wait_for(asyncio.to_thread(drive.drive_roots), timeout=60)
            path = await asyncio.wait_for(asyncio.to_thread(drive.find_folder, folder_id), timeout=60) if roots else None
        except TimeoutError:
            return web.json_response({"ok": False, "error": (
                "Google Drive is taking too long to open. If macOS asked for permission to access it, click Allow and try again."
            )}, status=504)
        if not roots:
            return web.json_response({**base, "status": "no_drive"})
        if not path:
            return web.json_response({**base, "status": "not_added"})
        try:
            result = await asyncio.to_thread(sharing.configure, str(path), str(body.get("name", "")))
        except (sharing.SharingError, OSError) as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        recompile()
        # Drive streams files on first use; fetch them now so the first in-game sound isn't late
        asyncio.get_running_loop().run_in_executor(None, sharing.warm_cache)
        return web.json_response({**base, "status": "joined", **result, **await asyncio.to_thread(sharing_state)})

    @routes.get("/api/sharing/invite")
    async def invite(_: web.Request) -> web.Response:
        """Links to hand out: the folder for admins, the library .zip for everyone else."""
        folder = sharing.shared_folder()
        if not folder:
            return web.json_response({"ok": False, "error": "Turn on the shared folder first"}, status=400)

        def ids() -> tuple[str | None, str | None]:
            packs.write_library(folder)
            lib = folder / packs.LIBRARY_NAME
            return drive.folder_id_of(folder), drive.item_id(lib) if lib.exists() else None

        folder_id, lib_id = await asyncio.to_thread(ids)
        out: dict = {"ok": True, "folder_link": drive.folder_link(folder_id) if folder_id else None, "library_link": None, "library_public": False}
        # Drive gives a new file a temporary local id until it has uploaded it
        if lib_id and not lib_id.startswith("local"):
            out["library_link"] = f"https://drive.google.com/file/d/{lib_id}/view?usp=sharing"
            try:
                out["library_public"] = await packs.check_link(out["library_link"])
            except Exception:
                pass
        return web.json_response(out)

    @routes.get("/api/pack/export")
    async def export_pack(_: web.Request) -> web.Response:
        name = sharing.settings().name
        data = await asyncio.to_thread(packs.export_pack, name)
        return web.Response(body=data, content_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{name} sound pack.zip"',
        })

    @routes.post("/api/packs")
    async def import_pack(request: web.Request) -> web.Response:
        known = {p["id"] for p in packs.list_packs()}
        try:
            if request.content_type == "application/json":
                url = str((await request.json()).get("url", "")).strip()
                data = await packs.download(url)
                record = await asyncio.to_thread(packs.import_pack, data, url)
            else:
                reader = await request.multipart()
                field = await reader.next()
                if field is None:
                    return web.json_response({"ok": False, "error": "No file uploaded"}, status=400)
                data = bytearray()
                while chunk := await field.read_chunk():  # type: ignore[union-attr]
                    data += chunk
                    if len(data) > packs.MAX_PACK_BYTES:
                        return web.json_response({"ok": False, "error": "Pack is larger than 200 MB"}, status=400)
                record = await asyncio.to_thread(packs.import_pack, bytes(data), None)
        except packs.PackError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        except Exception as e:
            return web.json_response({"ok": False, "error": f"Couldn't import the pack: {e}"}, status=400)
        if record.get("library") and record["id"] not in known:
            # A shared library is for playing: its sounds play in your games straight away
            sharing.set_following(f"{sharing.PACK_PREFIX}{record['id']}", True)
        recompile()
        sharing.publish_safely()
        return web.json_response({"ok": True, "pack": {"id": record["id"], "name": record["name"], "library": record.get("library", False)}, **await asyncio.to_thread(sharing_state)})

    @routes.post("/api/packs/{id}/refresh")
    async def refresh_pack(request: web.Request) -> web.Response:
        pack = packs.load_pack(request.match_info["id"])
        if not pack:
            raise web.HTTPNotFound()
        try:
            changed = await packs.refresh(pack)
        except Exception as e:
            return web.json_response({"ok": False, "error": f"Couldn't update {pack['name']}: {e}"}, status=400)
        if changed:
            recompile()
        return web.json_response({"ok": True, "changed": changed, **await asyncio.to_thread(sharing_state)})

    @routes.delete("/api/packs/{id}")
    async def remove_pack(request: web.Request) -> web.Response:
        pack_id = request.match_info["id"]
        packs.remove_pack(pack_id)
        sharing.set_following(f"{sharing.PACK_PREFIX}{pack_id}", False)
        recompile()
        return web.json_response({"ok": True, **await asyncio.to_thread(sharing_state)})

    app.add_routes(routes)
