from __future__ import annotations

import asyncio
import json
import logging
import secrets
import tempfile
import wave
from pathlib import Path
from urllib.parse import quote, urlparse

from aiohttp import web
from pydantic import BaseModel, Field, ValidationError

from src.sound import SoundManager

logger = logging.getLogger(__name__)

SOUNDBOARD_PATH = Path("soundboard.json")
CLIPS_DIR = Path("media/soundboard")
# Same limit as Discord's soundboard. The editor trims to this before upload.
MAX_CLIP_SECONDS = 5.2
# A 5.2 s clip as 48 kHz 16-bit stereo WAV is about 1 MB
MAX_CLIP_BYTES = 2 * 1024 * 1024
# Limits for audio pulled from a link (YouTube etc.) before it is trimmed in the browser
MAX_SOURCE_SECONDS = 20 * 60
MAX_SOURCE_BYTES = 60 * 1024 * 1024


class ClipMeta(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    emoji: str = Field(default="", max_length=16)
    volume: int = Field(default=100, ge=0, le=100)


class Clip(ClipMeta):
    id: str
    file: str
    duration: float


def _load() -> list[Clip]:
    if not SOUNDBOARD_PATH.exists():
        return []
    text = SOUNDBOARD_PATH.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [Clip.model_validate(c) for c in json.loads(text).get("clips", [])]


def _save(clips: list[Clip]) -> None:
    # Encode before opening so a failure can't truncate the existing file. UTF-8 explicitly:
    # the Windows default (cp1252) can't hold emoji.
    data = json.dumps({"clips": [c.model_dump() for c in clips]}, indent=4, ensure_ascii=False)
    SOUNDBOARD_PATH.write_bytes(data.encode("utf-8"))


def _errors(e: ValidationError) -> list[dict]:
    return [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()]


def _wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, ZeroDivisionError):
        return None


def _download_audio(url: str, out_dir: Path) -> tuple[Path, str]:
    """Fetch the audio track of a YouTube (or any yt-dlp supported) link without re-encoding."""
    import yt_dlp

    def too_long(info: dict, *, incomplete: bool) -> str | None:
        duration = info.get("duration")
        if duration and duration > MAX_SOURCE_SECONDS:
            return f"Video is longer than {MAX_SOURCE_SECONDS // 60} minutes"
        return None

    opts = {
        # m4a/AAC decodes in every browser; fall back to any audio, then a full video
        "format": "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best",
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_SOURCE_BYTES,
        "match_filter": too_long,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    files = list(out_dir.glob("source.*"))
    if not files:
        raise ValueError("Nothing was downloaded (too long or too large?)")
    return files[0], info.get("title") or "clip"


def setup_soundboard(app: web.Application, sound: SoundManager) -> None:
    """Mount the soundboard API: trimmed WAV clips with a name, emoji and volume, played on the app's speakers."""

    def find(clips: list[Clip], clip_id: str) -> Clip:
        for c in clips:
            if c.id == clip_id:
                return c
        raise web.HTTPNotFound(text=json.dumps({"ok": False, "error": "Unknown clip"}), content_type="application/json")

    async def list_clips(_: web.Request) -> web.Response:
        return web.json_response({"clips": [c.model_dump() for c in _load()], "max_seconds": MAX_CLIP_SECONDS})

    async def create_clip(request: web.Request) -> web.Response:
        # multipart: "meta" (JSON name/emoji/volume) then "file" (the trimmed WAV the editor rendered)
        reader = await request.multipart()
        meta_field = await reader.next()
        if meta_field is None or meta_field.name != "meta":  # type: ignore[union-attr]
            return web.json_response({"ok": False, "error": "Missing clip details"}, status=400)
        try:
            meta = ClipMeta.model_validate_json(await meta_field.read())  # type: ignore[union-attr]
        except ValidationError as e:
            return web.json_response({"ok": False, "errors": _errors(e)}, status=422)
        file_field = await reader.next()
        if file_field is None or file_field.name != "file":  # type: ignore[union-attr]
            return web.json_response({"ok": False, "error": "Missing audio"}, status=400)

        CLIPS_DIR.mkdir(parents=True, exist_ok=True)
        clip_id = secrets.token_hex(4)
        dest = CLIPS_DIR / f"{clip_id}.wav"
        size = 0
        with dest.open("wb") as f:
            while chunk := await file_field.read_chunk():  # type: ignore[union-attr]
                size += len(chunk)
                if size > MAX_CLIP_BYTES:
                    break
                f.write(chunk)
        duration = _wav_duration(dest) if size <= MAX_CLIP_BYTES else None
        if duration is None or duration > MAX_CLIP_SECONDS + 0.05:
            dest.unlink()
            return web.json_response({"ok": False, "error": f"Clips must be a WAV of at most {MAX_CLIP_SECONDS} seconds"}, status=400)

        clip = Clip(id=clip_id, file=dest.as_posix(), duration=round(duration, 3), **meta.model_dump())
        _save([*_load(), clip])
        logger.info(f"Soundboard clip added: {clip.name} ({clip.duration}s)")
        return web.json_response({"ok": True, "clip": clip.model_dump()})

    async def update_clip(request: web.Request) -> web.Response:
        clips = _load()
        clip = find(clips, request.match_info["id"])
        try:
            meta = ClipMeta.model_validate({**clip.model_dump(), **await request.json()})
        except ValidationError as e:
            return web.json_response({"ok": False, "errors": _errors(e)}, status=422)
        updated = clip.model_copy(update=meta.model_dump())
        _save([updated if c.id == clip.id else c for c in clips])
        return web.json_response({"ok": True, "clip": updated.model_dump()})

    async def delete_clip(request: web.Request) -> web.Response:
        clips = _load()
        clip = find(clips, request.match_info["id"])
        Path(clip.file).unlink(missing_ok=True)
        _save([c for c in clips if c.id != clip.id])
        logger.info(f"Soundboard clip deleted: {clip.name}")
        return web.json_response({"ok": True})

    async def play_clip(request: web.Request) -> web.Response:
        clip = find(_load(), request.match_info["id"])
        await sound.play(clip.file, volume=clip.volume / 100)
        return web.json_response({"ok": True})

    async def fetch_link(request: web.Request) -> web.StreamResponse:
        url = str((await request.json()).get("url", "")).strip()
        if urlparse(url).scheme not in ("http", "https"):
            return web.json_response({"ok": False, "error": "Paste a full link starting with https://"}, status=400)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                path, title = await asyncio.get_running_loop().run_in_executor(None, _download_audio, url, Path(tmp))
            except Exception as e:
                logger.warning(f"Soundboard link fetch failed for {url}: {e}")
                msg = str(e).removeprefix("ERROR: ").split("\n")[0]
                return web.json_response({"ok": False, "error": msg or "Couldn't get audio from that link"}, status=400)
            body = path.read_bytes()
        logger.info(f"Soundboard fetched {title!r} from {url} ({len(body)} bytes)")
        # The browser decodes and trims it, then uploads the clip like a local file
        return web.Response(body=body, content_type="application/octet-stream", headers={"X-Title": quote(title)})

    async def stop_all(_: web.Request) -> web.Response:
        sound.stop_all()
        return web.json_response({"ok": True})

    app.router.add_get("/api/soundboard", list_clips)
    app.router.add_post("/api/soundboard", create_clip)
    app.router.add_patch("/api/soundboard/{id}", update_clip)
    app.router.add_delete("/api/soundboard/{id}", delete_clip)
    app.router.add_post("/api/soundboard/{id}/play", play_clip)
    app.router.add_post("/api/soundboard/stop", stop_all)
    app.router.add_post("/api/soundboard/fetch", fetch_link)
