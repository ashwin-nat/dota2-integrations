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
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from src import osutil, shortcuts
from src.media import LOCAL_MEDIA_DIR, media_dir, media_ref, set_media_dir, unique_path
from src.rules.config import ActionType, RulesConfig, sound_refs

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
    if folder and (target := shortcuts.follow(folder)) != folder:
        # Saved before shortcuts were followed
        _settings = _settings.model_copy(update={"folder": str(target)})
        _save()
        folder = target
    if folder and not folder.is_dir():
        # Drive not mounted yet, or the folder was removed: keep working from local files
        logger.warning(f"Shared folder {folder} is not available; using local media/ for now")
        set_media_dir(LOCAL_MEDIA_DIR)
    else:
        set_media_dir(folder / "media" if folder else LOCAL_MEDIA_DIR)
    LOCAL_MEDIA_DIR.mkdir(exist_ok=True)
    _restore_missing_media()
    return _settings


def reconnect() -> bool:
    """Switch to the shared folder if it has appeared since load() (Drive mounted late).

    Returns True if it switched, so the caller can reload rules and warm the cache.
    """
    folder = shared_folder()
    if not folder or media_dir() == folder / "media" or not folder.is_dir():
        return False
    set_media_dir(folder / "media")
    _restore_missing_media()
    logger.info(f"Shared folder {folder} is available again; playing sounds from it")
    return True


def _referenced_media() -> set[str]:
    """Sound files (as "media/<name>") that rules.json and soundboard.json point at."""
    refs: set[str] = set()
    try:
        if RULES_PATH.exists():
            raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
            for rule in raw["rules"] if isinstance(raw, dict) else raw:
                refs.update(f for a in rule.get("actions", []) for f in sound_refs(a))
        if SOUNDBOARD_PATH.exists():
            refs.update(c["file"] for c in json.loads(SOUNDBOARD_PATH.read_text(encoding="utf-8")).get("clips", []) if c.get("file"))
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.warning(f"Could not read sound references: {e}")
    return {r for r in refs if r.startswith("media/")}


def _restore_missing_media() -> None:
    """Copy local sounds your rules use into the shared media folder when it lacks them.

    Covers sounds that were in the local media/ folder before sharing was turned on, so
    rules never end up pointing at files only this PC has. Never overwrites or renames, and
    only touches sounds that are actually referenced, so deleted ones aren't resurrected.
    """
    folder = shared_folder()
    if not folder or not folder.is_dir():
        return
    dst = folder / "media"
    copied = 0
    for ref in _referenced_media():
        name = ref.removeprefix("media/")
        src = LOCAL_MEDIA_DIR / name
        if src.is_file() and not (dst / name).exists():
            try:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst / name)
                copied += 1
            except OSError as e:
                logger.warning(f"Could not copy {name} to the shared folder: {e}")
    if copied:
        logger.info(f"Copied {copied} of your sound(s) into the shared folder so your rules can find them")


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
                if action.get("type") == ActionType.PLAY_SOUND:
                    for c in action.get("clips", []):
                        c["file"] = renamed.get(c.get("file"), c.get("file"))
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
        _settings = _settings.model_copy(update={"folder": None, "name": name})
        _save()
        set_media_dir(LOCAL_MEDIA_DIR)
        logger.info("Sharing turned off")
        return {"copied": copied}

    path = Path(folder).expanduser()
    if not path.is_absolute():
        raise SharingError("Pick a folder from the list, or paste its full path")
    path = shortcuts.follow(path)
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
    # From wherever your rules' sounds are now: local media/, or the folder you're leaving
    current = media_dir()
    copied = _bring_media(current, path / "media") if current.resolve() != (path / "media").resolve() else 0
    old = shared_folder()
    if old and old != path and _settings.name:
        # Leave the old folder clean if we moved
        _person_path(old, _settings.name).unlink(missing_ok=True)
    elif old == path and _settings.name != name:
        _person_path(path, _settings.name).unlink(missing_ok=True)
    _settings = _settings.model_copy(update={"folder": str(path), "name": name})
    _save()
    set_media_dir(path / "media")
    # Sharing is on whatever happens next; a rule with a missing sound only stops the publish
    publish_safely()
    logger.info(f"Sharing on: {path} as {name} ({copied} sounds copied in)")
    return {"copied": copied}


def publish() -> None:
    """Write this person's rules and soundboard clips to the shared folder."""
    folder = shared_folder()
    if not folder or not folder.is_dir():
        return
    rules: list = []
    if RULES_PATH.exists():
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        # Never publish rules whose sounds aren't there; friends could not copy them anyway
        RulesConfig.model_validate(raw)
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
        "platform": osutil.platform_name(),
        "rules": [r for r in rules if r["actions"]],
        "soundboard": clips,
    }
    (folder / PEOPLE_DIR).mkdir(parents=True, exist_ok=True)
    _write_atomic(_person_path(folder, _settings.name), json.dumps(data, indent=2, ensure_ascii=False))


def warm_cache() -> None:
    """Read every shared sound once, so Drive for desktop keeps a local copy to play from."""
    folder = shared_folder()
    media = folder / "media" if folder else None
    if not media or not media.is_dir():
        return
    for f in media.iterdir():
        try:
            with open(f, "rb") as fh:
                while fh.read(1 << 20):
                    pass
        except OSError:
            pass


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
        })
    return out
