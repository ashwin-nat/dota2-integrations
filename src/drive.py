"""Find a Google Drive folder on this computer from its share link.

Drive for desktop keeps a folder someone shared with you, once added to My Drive as a
shortcut, under <account>/.shortcut-targets-by-id/<folder id>/<folder name>. On macOS
every synced item also carries its Drive id in the com.google.drivefs.item-id#S extended
attribute, which is how we find a folder you own and build an invite link for it.
"""
from __future__ import annotations

import re
from pathlib import Path

from src import osutil

SHORTCUTS_DIR = ".shortcut-targets-by-id"
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
    return osutil.google_drive_roots()


def item_id(path: Path) -> str | None:
    """The Drive id of a synced file or folder (macOS only)."""
    return osutil.google_drive_item_id(path)


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
        if osutil.CAN_READ_DRIVE_ITEM_IDS:
            top = _subdirs(root / "My Drive")
            for d in top + [s for t in top for s in _subdirs(t)]:
                if item_id(d) == folder_id:
                    return d
    return None
