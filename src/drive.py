"""Find a Google Drive folder on this computer from its share link.

Drive for desktop keeps a folder someone shared with you, once added to My Drive as a
shortcut, under <account>/.shortcut-targets-by-id/<folder id>/<folder name>. On macOS
every synced item also carries its Drive id in the com.google.drivefs.item-id#S extended
attribute, which is how we find a folder you own and build an invite link for it.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import string
import sys
from pathlib import Path

SHORTCUTS_DIR = ".shortcut-targets-by-id"
ITEM_ID_ATTR = b"com.google.drivefs.item-id#S"
DOWNLOAD_URL = "https://www.google.com/drive/download/"

_ID = r"[\w-]{20,}"


def folder_id_from_link(text: str) -> str | None:
    """The folder id in a Drive folder link, a whole invite message holding one, or a bare id."""
    text = text.strip()
    if m := re.search(rf"/folders/({_ID})", text) or re.search(rf"[?&]id=({_ID})", text):
        return m.group(1)
    return text if re.fullmatch(_ID, text) else None


def folder_link(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


def drive_roots() -> list[Path]:
    """Each signed-in Google Drive for desktop account on this computer."""
    if sys.platform == "darwin":
        cloud = Path.home() / "Library" / "CloudStorage"
        return sorted(d for d in cloud.glob("GoogleDrive-*") if d.is_dir()) if cloud.is_dir() else []
    if sys.platform == "win32":
        roots = [Path(f"{letter}:\\") for letter in string.ascii_uppercase]
        return [r for r in roots if (r / "My Drive").is_dir()]
    return []


_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True) if sys.platform == "darwin" else None


def item_id(path: Path) -> str | None:
    """The Drive id of a synced file or folder (macOS only)."""
    if _libc is None:
        return None
    buf = ctypes.create_string_buffer(256)
    n = _libc.getxattr(os.fsencode(path), ITEM_ID_ATTR, buf, len(buf), 0, 0)
    return buf.raw[:n].decode() if n > 0 else None


def folder_id_of(path: Path) -> str | None:
    """The Drive id of a synced folder, for invite links."""
    parts = path.parts
    if SHORTCUTS_DIR in parts and len(parts) > parts.index(SHORTCUTS_DIR) + 1:
        i = parts.index(SHORTCUTS_DIR)
        # <id>/<name> is the shared folder itself; deeper means a subfolder of it
        if len(parts) == i + 3:
            return parts[i + 1]
    return item_id(path)


def _subdirs(path: Path) -> list[Path]:
    try:
        return [d for d in path.iterdir() if d.is_dir() and not d.name.startswith(".")]
    except OSError:
        return []


def find_folder(folder_id: str) -> Path | None:
    """Where the Drive folder with this id is synced on this computer, if it is."""
    for root in drive_roots():
        # Shared with you and added to My Drive
        target = root / SHORTCUTS_DIR / folder_id
        if target.is_dir():
            inside = _subdirs(target)
            if len(inside) == 1:
                return inside[0]
        # Your own folder: look two levels into My Drive
        if _libc is not None:
            top = _subdirs(root / "My Drive")
            for d in top + [s for t in top for s in _subdirs(t)]:
                if item_id(d) == folder_id:
                    return d
    return None
