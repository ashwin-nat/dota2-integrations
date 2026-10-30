"""Share sounds and rules with friends through a synced folder (Google Drive, Dropbox, ...).

Layout of the shared folder:

    <folder>/media/           everyone's sound files and soundboard clips
    <folder>/people/<name>.json  one file per person: their rules and soundboard clips

Each person only ever writes their own people/<name>.json, so the sync service never
has two writers for one file. Lighting settings, logs and rules.json stay local.
"""
from __future__ import annotations

import filecmp
import getpass
import json
import logging
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from src import packs
from src.media import LOCAL_MEDIA_DIR, media_ref, set_media_dir, unique_path
from src.rules.config import ActionType, Rule

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path("sharing.json")
RULES_PATH = Path("rules.json")
SOUNDBOARD_PATH = Path("soundboard.json")
PEOPLE_DIR = "people"
PACK_PREFIX = "pack:"


def _default_name() -> str:
    try:
        return clean_name(getpass.getuser()).title() or "Player"
    except Exception:
        return "Player"


def clean_name(name: str) -> str:
    return re.sub(r"[^\w\- ]+", "", name).strip()[:24]


class SharingSettings(BaseModel):
    folder: str | None = None
    name: str = Field(default_factory=_default_name)
    # Friends (by name) and packs ("pack:<id>") whose rule sounds also play on this PC,
    # in the order they were followed
    following: list[str] = Field(default_factory=list)
    # Identifies this install so two friends can't publish under the same name
    device: str = Field(default_factory=lambda: uuid.uuid4().hex)


_settings = SharingSettings()


def settings() -> SharingSettings:
    return _settings


def shared_folder() -> Path | None:
    return Path(_settings.folder) if _settings.folder else None


def load() -> SharingSettings:
    """Read sharing.json and point media/ at the shared folder if sharing is on."""
    global _settings
    if SETTINGS_PATH.exists():
        try:
            _settings = SharingSettings.model_validate_json(SETTINGS_PATH.read_text(encoding="utf-8"))
        except ValidationError as e:
            logger.warning(f"Ignoring invalid {SETTINGS_PATH}: {e}")
    else:
        _save()
    folder = shared_folder()
    if folder and not folder.is_dir():
        # Drive not mounted yet, or the folder was removed: keep working from local files
        logger.warning(f"Shared folder {folder} is not available; using local media/ for now")
        set_media_dir(LOCAL_MEDIA_DIR)
    else:
        set_media_dir(folder / "media" if folder else LOCAL_MEDIA_DIR)
    LOCAL_MEDIA_DIR.mkdir(exist_ok=True)
    return _settings


def _save() -> None:
    SETTINGS_PATH.write_text(_settings.model_dump_json(indent=4), encoding="utf-8")


def _write_atomic(path: Path, text: str) -> None:
    # Sync clients may upload a file mid-write; replace it in one step instead
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _bring_media(src: Path, dst: Path) -> int:
    """Copy src's sounds into dst, keeping your rules and clips pointing at your own sounds.

    A file that already exists in dst with the same content is shared as is. One with the
    same name but different content (two people's "wow.mp3") is copied under a new name,
    and rules.json / soundboard.json are rewritten to use it. Returns how many were copied.
    """
    if not src.is_dir():
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    copied, renamed = 0, {}
    for f in src.iterdir():
        if not f.is_file() or f.name.startswith("."):
            continue
        target = dst / f.name
        if target.exists():
            if filecmp.cmp(f, target, shallow=False):
                continue
            target = unique_path(dst, f.name)
            renamed[media_ref(f)] = media_ref(target)
        shutil.copy2(f, target)
        copied += 1
    if renamed:
        _rewrite_refs(renamed)
    return copied


def _rewrite_refs(renamed: dict[str, str]) -> None:
    if RULES_PATH.exists():
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        for rule in raw["rules"] if isinstance(raw, dict) else raw:
            for action in rule.get("actions", []):
                if action.get("type") == ActionType.PLAY_SOUND and action.get("file") in renamed:
                    action["file"] = renamed[action["file"]]
        _write_atomic(RULES_PATH, json.dumps(raw, indent=4))
    if SOUNDBOARD_PATH.exists():
        board = json.loads(SOUNDBOARD_PATH.read_text(encoding="utf-8"))
        for clip in board.get("clips", []):
            if clip.get("file") in renamed:
                clip["file"] = renamed[clip["file"]]
        _write_atomic(SOUNDBOARD_PATH, json.dumps(board, indent=4, ensure_ascii=False))
    logger.info(f"Renamed {len(renamed)} sound(s) that clashed with a different file of the same name: {renamed}")


def _person_path(folder: Path, name: str) -> Path:
    return folder / PEOPLE_DIR / f"{name}.json"


def _read_person(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        # Often a file the sync client is still downloading
        logger.warning(f"Skipping unreadable shared file {path}: {e}")
        return None
    return data if isinstance(data, dict) else None


class SharingError(ValueError):
    pass


def configure(folder: str | None, name: str, create: bool = False) -> dict:
    """Turn sharing on (or move it) to `folder`, or off when folder is None. Returns copy counts."""
    global _settings
    name = clean_name(name)
    if not name:
        raise SharingError("Pick a name your friends will recognise")
    if folder is None:
        old = shared_folder()
        # Bring the shared sounds home so rules keep working without the folder
        copied = _bring_media(old / "media", LOCAL_MEDIA_DIR) if old and old.is_dir() else 0
        if old and old.is_dir():
            _person_path(old, _settings.name).unlink(missing_ok=True)
        # Packs don't need the folder, so keep following those
        packs_followed = [k for k in _settings.following if k.startswith(PACK_PREFIX)]
        _settings = _settings.model_copy(update={"folder": None, "name": name, "following": packs_followed})
        _save()
        set_media_dir(LOCAL_MEDIA_DIR)
        logger.info("Sharing turned off")
        return {"copied": copied}

    path = Path(folder).expanduser()
    if not path.is_absolute():
        raise SharingError("Pick a folder from the list, or paste its full path")
    if create:
        if not path.parent.is_dir():
            raise SharingError(f"{path.parent} doesn't exist")
        path.mkdir(exist_ok=True)
    if not path.is_dir():
        raise SharingError(f"{path} isn't a folder")
    existing = _read_person(_person_path(path, name)) if _person_path(path, name).exists() else None
    if existing and existing.get("device") not in (None, _settings.device):
        raise SharingError(f"Someone else in this folder already uses the name {name!r}. Pick another.")

    (path / PEOPLE_DIR).mkdir(exist_ok=True)
    copied = _bring_media(LOCAL_MEDIA_DIR, path / "media")
    old = shared_folder()
    if old and old != path and _settings.name:
        # Leave the old folder clean if we moved
        _person_path(old, _settings.name).unlink(missing_ok=True)
    elif old == path and _settings.name != name:
        _person_path(path, _settings.name).unlink(missing_ok=True)
    _settings = _settings.model_copy(update={"folder": str(path), "name": name})
    _save()
    set_media_dir(path / "media")
    publish()
    logger.info(f"Sharing on: {path} as {name} ({copied} local sounds copied in)")
    return {"copied": copied}


def set_following(name: str, follow: bool) -> None:
    global _settings
    following = [n for n in _settings.following if n != name] + ([name] if follow else [])
    _settings = _settings.model_copy(update={"following": following})
    _save()


def publish() -> None:
    """Write this person's rules and soundboard clips to the shared folder."""
    folder = shared_folder()
    if not folder or not folder.is_dir():
        return
    rules: list = []
    if RULES_PATH.exists():
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        rules = raw["rules"] if isinstance(raw, dict) else raw
    # Webhooks can carry API keys and only make sense on the owner's network
    rules = [
        {**r, "actions": [a for a in r.get("actions", []) if a.get("type") != ActionType.WEBHOOK]}
        for r in rules
    ]
    clips = []
    if SOUNDBOARD_PATH.exists():
        clips = json.loads(SOUNDBOARD_PATH.read_text(encoding="utf-8")).get("clips", [])
    data = {
        "name": _settings.name,
        "device": _settings.device,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": sys.platform,
        "rules": [r for r in rules if r["actions"]],
        "soundboard": clips,
    }
    (folder / PEOPLE_DIR).mkdir(parents=True, exist_ok=True)
    _write_atomic(_person_path(folder, _settings.name), json.dumps(data, indent=2, ensure_ascii=False))


def publish_safely() -> None:
    """publish(), but a sync folder hiccup only logs instead of failing the caller."""
    try:
        publish()
    except (OSError, ValueError) as e:
        logger.warning(f"Could not publish to the shared folder: {e}")


def friends() -> list[dict]:
    """Everyone else's published file in the shared folder."""
    folder = shared_folder()
    if not folder or not (folder / PEOPLE_DIR).is_dir():
        return []
    out = []
    for path in sorted((folder / PEOPLE_DIR).glob("*.json"), key=lambda p: p.stem.lower()):
        if path.stem == _settings.name:
            continue
        data = _read_person(path)
        if data is None or data.get("device") == _settings.device:
            continue
        out.append({
            "key": path.stem,
            "kind": "friend",
            "name": path.stem,
            "updated": data.get("updated"),
            "rules": data.get("rules", []),
            "soundboard": data.get("soundboard", []),
            "following": path.stem in _settings.following,
        })
    return out


def _trigger(monitor: object) -> str:
    m = monitor.model_dump(mode="json") if hasattr(monitor, "model_dump") else dict(monitor or {})  # type: ignore[union-attr]
    # Blink has its own monitor type but is the same trigger as an item rule on item_blink
    if m.get("type") == "blink":
        m = {"type": "item", "target": "item_blink", "event": m.get("event")}
    return f"{m.get('type')}|{m.get('target', '')}|{m.get('event')}"


def followed_rules(own_rules: list[Rule]) -> list[Rule]:
    """Sound actions from the rules of friends this person follows, ready to compile.

    Only sounds: a friend's light colours and priorities are for their room. Sounds never
    stack: a trigger you already have a sound for keeps yours, and when several followed
    friends use the same trigger, the friend you followed first wins.
    """
    folder = shared_folder()
    taken = {
        _trigger(r.monitor) for r in own_rules
        if any(a.type == ActionType.PLAY_SOUND and a.enabled for a in r.actions)
    }
    out: list[Rule] = []
    for key in _settings.following:
        if key.startswith(PACK_PREFIX):
            data = packs.load_pack(key.removeprefix(PACK_PREFIX))
            name = data["name"] if data else key
        else:
            path = _person_path(folder, key) if folder else None
            data = _read_person(path) if path and path.exists() else None
            name = key
        if not data:
            continue
        for raw in data.get("rules", []):
            sounds = [a for a in raw.get("actions", []) if a.get("type") == ActionType.PLAY_SOUND and a.get("enabled", True)]
            if not sounds or _trigger(raw.get("monitor")) in taken:
                continue
            taken.add(_trigger(raw.get("monitor")))
            try:
                out.append(Rule.model_validate({"id": f"{name}/{raw.get('id')}", "monitor": raw.get("monitor"), "actions": sounds}))
            except ValidationError as e:
                logger.warning(f"Skipping {name}'s rule {raw.get('id')!r}: {e.error_count()} problem(s)")
    return out


def followed_signature() -> tuple:
    """Changes whenever a followed friend's file changes, so the engine knows to recompile."""
    folder = shared_folder()
    sig = []
    for key in sorted(_settings.following):
        if key.startswith(PACK_PREFIX):
            path: Path | None = packs.PACKS_DIR / f"{key.removeprefix(PACK_PREFIX)}.json"
        else:
            path = _person_path(folder, key) if folder else None
        try:
            sig.append((key, path.stat().st_mtime_ns if path else None))
        except OSError:
            sig.append((key, None))
    return tuple(sig)
