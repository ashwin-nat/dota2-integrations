"""Share sounds and rules with friends through a synced folder (Google Drive, Dropbox, ...).

Layout of the shared folder:

    <folder>/media/           everyone's sound files and soundboard clips
    <folder>/people/<name>.json  one file per person: their rules and soundboard clips

Each person only ever writes their own people/<name>.json, so the sync service never
has two writers for one file. Lighting settings, logs and rules.json stay local.
"""
from __future__ import annotations

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

from src.media import LOCAL_MEDIA_DIR, set_media_dir
from src.rules.config import ActionType, Rule

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path("sharing.json")
RULES_PATH = Path("rules.json")
SOUNDBOARD_PATH = Path("soundboard.json")
PEOPLE_DIR = "people"


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
    # Friends whose rule sounds also play on this PC
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


def _copy_missing(src: Path, dst: Path) -> int:
    if not src.is_dir():
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in src.iterdir():
        if f.is_file() and not f.name.startswith(".") and not (dst / f.name).exists():
            shutil.copy2(f, dst / f.name)
            copied += 1
    return copied


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
        copied = _copy_missing(old / "media", LOCAL_MEDIA_DIR) if old and old.is_dir() else 0
        if old and old.is_dir():
            _person_path(old, _settings.name).unlink(missing_ok=True)
        _settings =_settings.model_copy(update={"folder": None, "name": name, "following": []})
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
    copied = _copy_missing(LOCAL_MEDIA_DIR, path / "media")
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
            "name": path.stem,
            "updated": data.get("updated"),
            "rules": data.get("rules", []),
            "soundboard": data.get("soundboard", []),
            "following": path.stem in _settings.following,
        })
    return out


def followed_rules() -> list[Rule]:
    """Sound actions from the rules of friends this person follows, ready to compile.

    Only sounds: a friend's light colours and priorities are for their room.
    """
    folder = shared_folder()
    if not folder:
        return []
    out: list[Rule] = []
    for name in _settings.following:
        path = _person_path(folder, name)
        data = _read_person(path) if path.exists() else None
        if not data:
            continue
        for raw in data.get("rules", []):
            sounds = [a for a in raw.get("actions", []) if a.get("type") == ActionType.PLAY_SOUND and a.get("enabled", True)]
            if not sounds:
                continue
            try:
                out.append(Rule.model_validate({"id": f"{name}/{raw.get('id')}", "monitor": raw.get("monitor"), "actions": sounds}))
            except ValidationError as e:
                logger.warning(f"Skipping {name}'s rule {raw.get('id')!r}: {e.error_count()} problem(s)")
    return out


def followed_signature() -> tuple:
    """Changes whenever a followed friend's file changes, so the engine knows to recompile."""
    folder = shared_folder()
    if not folder:
        return ()
    sig = []
    for name in sorted(_settings.following):
        path = _person_path(folder, name)
        try:
            sig.append((name, path.stat().st_mtime_ns))
        except OSError:
            sig.append((name, None))
    return tuple(sig)
