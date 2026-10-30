"""Sound packs: one .zip holding someone's rules, soundboard clips and the sounds they use.

A pack is the no-install way to share. Export yours, upload it anywhere (a Google Drive
file shared by link, Dropbox, Discord), and friends import it from the file or the link.
Packs imported from a link are re-downloaded now and then, so re-uploading a new version
of the same Drive file (Manage versions keeps the link) updates everyone.

Imported packs are kept in packs/<id>.json. Their sounds go into the media folder, and a
sound whose name clashes with a different file is stored under a new name, with the pack's
rules and clips rewritten to match.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import ssl
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import aiohttp
import certifi

from src.config_ui.files import AUDIO_EXTENSIONS
from src.media import media_dir, media_ref, resolve, unique_path
from src.rules.config import ActionType

logger = logging.getLogger(__name__)

PACKS_DIR = Path("packs")
RULES_PATH = Path("rules.json")
SOUNDBOARD_PATH = Path("soundboard.json")
FORMAT = 1
MAX_PACK_BYTES = 200 * 1024 * 1024
MAX_SOUND_BYTES = 25 * 1024 * 1024
MAX_SOUNDS = 500


class PackError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _without_webhooks(rules: list) -> list:
    # Webhooks can carry API keys and only make sense on the owner's network
    out = []
    for r in rules:
        actions = [a for a in r.get("actions", []) if a.get("type") != ActionType.WEBHOOK]
        if actions:
            out.append({**r, "actions": actions})
    return out


def export_pack(name: str) -> bytes:
    """Zip this install's rules, soundboard clips and every sound they use."""
    rules: list = []
    if RULES_PATH.exists():
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        rules = raw["rules"] if isinstance(raw, dict) else raw
    rules = _without_webhooks(rules)
    clips = json.loads(SOUNDBOARD_PATH.read_text(encoding="utf-8")).get("clips", []) if SOUNDBOARD_PATH.exists() else []
    refs = {a["file"] for r in rules for a in r["actions"] if a.get("type") == ActionType.PLAY_SOUND}
    refs |= {c["file"] for c in clips}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("pack.json", json.dumps({
            "format": FORMAT, "name": name, "created": _now(), "rules": rules, "soundboard": clips,
        }, indent=2, ensure_ascii=False))
        for ref in sorted(refs):
            path = resolve(ref)
            if ref.startswith("media/") and path.is_file():
                # MP3/OGG are already compressed; storing them is as small and much faster
                z.write(path, f"media/{path.name}", compress_type=zipfile.ZIP_STORED)
    return buf.getvalue()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "pack"


def _pack_path(pack_id: str) -> Path:
    return PACKS_DIR / f"{pack_id}.json"


def load_pack(pack_id: str) -> dict | None:
    if not re.fullmatch(r"[a-z0-9-]+", pack_id):
        return None
    path = _pack_path(pack_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        logger.warning(f"Skipping unreadable pack {path}: {e}")
        return None


def list_packs() -> list[dict]:
    if not PACKS_DIR.is_dir():
        return []
    packs = [load_pack(p.stem) for p in sorted(PACKS_DIR.glob("*.json"))]
    return [p for p in packs if p]


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def import_pack(data: bytes, source: str | None = None) -> dict:
    """Unpack a pack's sounds into the media folder and remember its rules and clips."""
    if len(data) > MAX_PACK_BYTES:
        raise PackError("Pack is larger than 200 MB")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        meta = json.loads(z.read("pack.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise PackError("That isn't a Rule Forge sound pack (no pack.json inside)") from e
    if not isinstance(meta, dict) or not isinstance(meta.get("rules", []), list):
        raise PackError("The pack's pack.json is damaged")
    name = str(meta.get("name") or "Pack")[:40]

    # Same link or same name again means an update of a pack we already have
    existing = next((p for p in list_packs() if (source and p.get("source") == source) or (not source and p["name"] == name)), None)
    pack_id = existing["id"] if existing else _slug(name)
    if not existing:
        n = 2
        while _pack_path(pack_id).exists():
            pack_id, n = f"{_slug(name)}-{n}", n + 1
    owned: dict[str, str] = (existing or {}).get("files", {})

    entries = [i for i in z.infolist() if i.filename.startswith("media/") and not i.is_dir()]
    if len(entries) > MAX_SOUNDS:
        raise PackError(f"Pack has more than {MAX_SOUNDS} sounds")
    folder = media_dir()
    folder.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    renamed: dict[str, str] = {}
    for info in entries:
        # Only flat media/<name> entries; Path(...).name also blocks ../ tricks
        base = Path(info.filename).name
        if Path(base).suffix.lower() not in AUDIO_EXTENSIONS or base.startswith("."):
            continue
        if info.file_size > MAX_SOUND_BYTES:
            raise PackError(f"{base} is larger than 25 MB")
        content = z.read(info)
        target = folder / owned.get(base, base)
        if target.exists() and target.read_bytes() != content and target.name not in owned.values():
            # Someone else's different sound already has this name
            target = unique_path(folder, base)
        if not target.exists() or target.read_bytes() != content:
            _write_atomic(target, content)
        files[base] = target.name
        if target.name != base:
            renamed[f"media/{base}"] = media_ref(target)

    rules = _without_webhooks(meta.get("rules", []))
    for r in rules:
        for a in r["actions"]:
            if a.get("type") == ActionType.PLAY_SOUND and a.get("file") in renamed:
                a["file"] = renamed[a["file"]]
    clips = [c for c in meta.get("soundboard", []) if isinstance(c, dict) and c.get("file")]
    for c in clips:
        c["file"] = renamed.get(c["file"], c["file"])

    record = {
        "id": pack_id,
        "name": name,
        "source": source,
        "sha256": hashlib.sha256(data).hexdigest(),
        "updated": meta.get("created"),
        "imported": _now(),
        "rules": rules,
        "soundboard": clips,
        "files": files,
    }
    PACKS_DIR.mkdir(exist_ok=True)
    _write_atomic(_pack_path(pack_id), json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8"))
    logger.info(f"Imported pack {name!r} ({len(rules)} rules, {len(files)} sounds){' from ' + source if source else ''}")
    return record


def remove_pack(pack_id: str) -> None:
    # Sounds stay: rules you copied from the pack may use them
    _pack_path(pack_id).unlink(missing_ok=True)


def download_url(url: str) -> str:
    """Turn a share link into a direct download link where the site needs it."""
    u = urlparse(url)
    host = u.netloc.lower()
    if host.endswith("drive.google.com") or host.endswith("docs.google.com"):
        m = re.search(r"/d/([\w-]{10,})", u.path)
        file_id = m.group(1) if m else (parse_qs(u.query).get("id") or [""])[0]
        if not file_id:
            raise PackError("That Google Drive link doesn't point at a file. Share the pack's .zip file, not a folder.")
        # confirm=t skips the "can't scan for viruses" page shown for larger files
        return f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    if host.endswith("dropbox.com"):
        q = parse_qs(u.query)
        q["dl"] = ["1"]
        return u._replace(query="&".join(f"{k}={v[0]}" for k, v in q.items())).geturl()
    return url


async def download(url: str) -> bytes:
    if urlparse(url).scheme not in ("http", "https"):
        raise PackError("Paste a full link starting with https://")
    connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async with session.get(download_url(url)) as resp:
            if resp.status in (401, 403, 404):
                raise PackError("Couldn't open that link. In Google Drive, set the file's access to \"Anyone with the link\".")
            resp.raise_for_status()
            data = bytearray()
            async for chunk in resp.content.iter_chunked(1 << 16):
                data += chunk
                if len(data) > MAX_PACK_BYTES:
                    raise PackError("Pack is larger than 200 MB")
    if not data.startswith(b"PK"):
        # Drive answers private files with a sign-in page instead of an error
        raise PackError("That link didn't give a .zip file. In Google Drive, set the file's access to \"Anyone with the link\".")
    return bytes(data)


async def refresh(pack: dict) -> bool:
    """Re-download a linked pack. Returns True if it changed."""
    if not pack.get("source"):
        return False
    data = await download(pack["source"])
    if hashlib.sha256(data).hexdigest() == pack.get("sha256"):
        return False
    await asyncio.to_thread(import_pack, data, pack["source"])
    return True
