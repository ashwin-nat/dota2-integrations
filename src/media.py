from __future__ import annotations

from pathlib import Path

# Rules and soundboard clips refer to sounds as "media/<file name>". That prefix
# resolves to the app's own media/ directory, or to <shared folder>/media when
# sharing with friends is turned on (see src/sharing.py).
LOCAL_MEDIA_DIR = Path("media")
_media_dir = LOCAL_MEDIA_DIR


def media_dir() -> Path:
    return _media_dir


def set_media_dir(path: Path) -> None:
    global _media_dir
    _media_dir = path


def media_ref(path: Path) -> str:
    """The "media/<name>" form stored in rules.json and soundboard.json."""
    return f"media/{path.name}"


def unique_path(folder: Path, name: str) -> Path:
    """folder/name, or "stem (2).ext" etc. if that name is taken."""
    stem, ext = Path(name).stem, Path(name).suffix
    path, n = folder / name, 2
    while path.exists():
        path, n = folder / f"{stem} ({n}){ext}", n + 1
    return path


def resolve(file: str) -> Path:
    if file.startswith("media/"):
        return _media_dir / file.removeprefix("media/")
    return Path(file)
