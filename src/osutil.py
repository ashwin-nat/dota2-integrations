"""Everything that behaves differently per operating system lives here.

The rest of the code calls these helpers and never looks at sys.platform itself.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import string
import subprocess
import sys
from pathlib import Path

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

DRIVE_ITEM_ID_ATTR = b"com.google.drivefs.item-id#S"


def platform_name() -> str:
    """sys.platform, for recording which system a person publishes from."""
    return sys.platform


def open_dir(folder: Path) -> None:
    """Show a folder in the system file manager."""
    if IS_WINDOWS:
        os.startfile(folder)  # type: ignore[attr-defined]
    elif IS_MACOS:
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])


def app_data_base() -> Path | None:
    """The folder holding per-user app data folders; None where the app keeps data in the working folder."""
    if IS_MACOS:
        return Path.home() / "Library" / "Application Support"
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA") or Path.home())
    return None


def cloud_folders() -> list[tuple[str, Path]]:
    """Likely sync folders (Google Drive, OneDrive, iCloud, ...) that exist on this computer."""
    home = Path.home()
    found: list[tuple[str, Path]] = []
    if IS_MACOS:
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
    elif IS_WINDOWS:
        for letter in string.ascii_uppercase:
            for sub in ("My Drive", "Shared drives"):
                p = Path(f"{letter}:\\") / sub
                if p.is_dir():
                    found.append((f"Google Drive · {sub} ({letter}:)", p))
        if os.environ.get("OneDrive"):
            found.append(("OneDrive", Path(os.environ["OneDrive"])))
    return found


def google_drive_roots() -> list[Path]:
    """Each signed-in Google Drive for desktop account on this computer."""
    if IS_MACOS:
        cloud = Path.home() / "Library" / "CloudStorage"
        return sorted(d for d in cloud.glob("GoogleDrive-*") if d.is_dir()) if cloud.is_dir() else []
    if IS_WINDOWS:
        roots = [Path(f"{letter}:\\") for letter in string.ascii_uppercase]
        return [r for r in roots if (r / "My Drive").is_dir()]
    return []


_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True) if IS_MACOS else None

#: Whether google_drive_item_id can work here (only macOS exposes the Drive id of a file)
CAN_READ_DRIVE_ITEM_IDS = _libc is not None


def google_drive_item_id(path: Path) -> str | None:
    """The Google Drive id of a synced file or folder (macOS only)."""
    if _libc is None:
        return None
    buf = ctypes.create_string_buffer(256)
    n = _libc.getxattr(os.fsencode(path), DRIVE_ITEM_ID_ATTR, buf, len(buf), 0, 0)
    return buf.raw[:n].decode() if n > 0 else None


def steam_roots() -> list[Path]:
    """Where Steam may be installed."""
    home = Path.home()
    if IS_MACOS:
        return [home / "Library" / "Application Support" / "Steam"]
    if IS_WINDOWS:
        roots = []
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        return roots + [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    return [home / ".steam" / "steam", home / ".local" / "share" / "Steam"]


def ansi_codec() -> str:
    """Codec of the system's legacy 8-bit strings, as stored in Windows .lnk files."""
    return "mbcs" if IS_WINDOWS else "latin-1"
