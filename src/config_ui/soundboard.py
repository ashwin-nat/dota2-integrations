from __future__ import annotations

import asyncio
import io
import itertools
import json
import logging
import secrets
import tempfile
import wave
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlparse

import lameenc
from aiohttp import web
from pydantic import BaseModel, Field, ValidationError

from src import sharing
from src.config_ui.files import safe_filename
from src.media import LOCAL_MEDIA_DIR, media_dir, media_ref, resolve
from src.rules.config import RulesConfig
from src.sound import SoundManager

logger = logging.getLogger(__name__)

SOUNDBOARD_PATH = Path("soundboard.json")
MP3_BITRATE = 192
# Same limit as Discord's soundboard. The editor trims to this before upload.
MAX_CLIP_SECONDS = 5.2
# The editor uploads the trimmed clip as WAV (5.2 s at 48 kHz 16-bit stereo is about 1 MB)
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
    # Friends see clip names and emoji from the shared folder
    sharing.publish_safely()


def _errors(e: ValidationError) -> list[dict]:
    return [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()]


def _wav_to_mp3(data: bytes) -> tuple[bytes, float]:
    """Encode the editor's trimmed 16-bit WAV as MP3. Returns the MP3 and its duration in seconds."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            pcm = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as e:
        raise ValueError(f"Not a WAV file: {e}") from e
    if width != 2 or channels not in (1, 2) or not 8000 <= rate <= 48000:
        raise ValueError("Expected 16-bit mono or stereo audio at 8-48 kHz")
    duration = len(pcm) / (rate * channels * width)
    if not 0 < duration <= MAX_CLIP_SECONDS + 0.05:
        raise ValueError(f"Clips can be at most {MAX_CLIP_SECONDS} seconds")
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(MP3_BITRATE)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    return bytes(encoder.encode(pcm) + encoder.flush()), duration


def _clip_path(name: str, current: str | None = None) -> Path:
    """media/<name>.mp3, numbered if another file already has that name."""
    stem = Path(safe_filename(f"{name}.mp3")).stem
    for n in itertools.count(1):
        path = media_dir() / (f"{stem}.mp3" if n == 1 else f"{stem} ({n}).mp3")
        if not path.exists() or media_ref(path) == current:
            return path
    raise AssertionError("unreachable")


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


def setup_soundboard(
    app: web.Application,
    sound: SoundManager,
    rules_path: Path,
    reload: Callable[[RulesConfig], bool],
) -> None:
    """Mount the soundboard API. Clips are MP3s in media/ named after the clip, so rules can use them too."""

    def retarget_rules(old: str, new: str | None) -> int:
        """Point rules at a renamed clip, or switch their sound off when it's deleted. Returns actions changed."""
        if not rules_path.exists():
            return 0
        raw = json.loads(rules_path.read_text(encoding="utf-8"))
        changed = 0
        for rule in raw["rules"] if isinstance(raw, dict) else raw:
            for action in rule.get("actions", []):
                if action.get("type") == "play_sound" and action.get("file") == old:
                    if new:
                        action["file"] = new
                    else:
                        action["enabled"] = False
                    changed += 1
        if not changed:
            return 0
        try:
            config = RulesConfig.model_validate(raw)
        except ValidationError as e:
            # Some other rule is already broken; still keep these references in step with the file
            logger.warning(f"rules.json has errors, saved clip change without reloading: {e}")
            rules_path.write_text(json.dumps(raw, indent=4))
            return changed
        rules_path.write_text(json.dumps(config.model_dump(mode="json"), indent=4))
        reload(config)
        logger.info(f"Updated {changed} rule sound(s) for {old} -> {new or 'removed'}")
        return changed

    def migrate_wav_clips() -> None:
        """Clips from the first soundboard version were WAVs in media/soundboard/; convert them to named MP3s."""
        clips = _load()
        changed = False
        for i, clip in enumerate(clips):
            old = Path(clip.file)
            if old.suffix != ".wav" or old.parent != LOCAL_MEDIA_DIR / "soundboard" or not old.is_file():
                continue
            try:
                mp3, _ = _wav_to_mp3(old.read_bytes())
            except ValueError as e:
                logger.warning(f"Could not convert soundboard clip {clip.name}: {e}")
                continue
            dest = _clip_path(clip.name)
            dest.write_bytes(mp3)
            clips[i] = clip.model_copy(update={"file": media_ref(dest)})
            retarget_rules(clip.file, media_ref(dest))
            old.unlink()
            changed = True
            logger.info(f"Converted soundboard clip {clip.file} -> {dest}")
        if changed:
            _save(clips)
            old_dir = LOCAL_MEDIA_DIR / "soundboard"
            if old_dir.is_dir() and not any(old_dir.iterdir()):
                old_dir.rmdir()

    migrate_wav_clips()

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

        data = bytearray()
        while chunk := await file_field.read_chunk():  # type: ignore[union-attr]
            data += chunk
            if len(data) > MAX_CLIP_BYTES:
                return web.json_response({"ok": False, "error": "Clip is too large"}, status=400)
        try:
            mp3, duration = await asyncio.get_running_loop().run_in_executor(None, _wav_to_mp3, bytes(data))
        except ValueError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

        media_dir().mkdir(parents=True, exist_ok=True)
        dest = _clip_path(meta.name)
        dest.write_bytes(mp3)
        clip = Clip(id=secrets.token_hex(4), file=media_ref(dest), duration=round(duration, 3), **meta.model_dump())
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
        renamed, rules_changed = None, 0
        dest = _clip_path(meta.name, current=clip.file)
        if media_ref(dest) != clip.file and resolve(clip.file).is_file():
            resolve(clip.file).rename(dest)
            updated.file = media_ref(dest)
            renamed = {"from": clip.file, "to": updated.file}
            rules_changed = retarget_rules(clip.file, updated.file)
        _save([updated if c.id == clip.id else c for c in clips])
        return web.json_response({"ok": True, "clip": updated.model_dump(), "renamed": renamed, "rules_changed": rules_changed})

    async def delete_clip(request: web.Request) -> web.Response:
        clips = _load()
        clip = find(clips, request.match_info["id"])
        # Switch off rule sounds first so rules.json never points an enabled action at a missing file
        rules_changed = retarget_rules(clip.file, None)
        resolve(clip.file).unlink(missing_ok=True)
        _save([c for c in clips if c.id != clip.id])
        logger.info(f"Soundboard clip deleted: {clip.name}")
        return web.json_response({"ok": True, "file": clip.file, "rules_changed": rules_changed})

    async def play_clip(request: web.Request) -> web.Response:
        clip = find(_load(), request.match_info["id"])
        await sound.play(str(resolve(clip.file)), volume=clip.volume / 100)
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
