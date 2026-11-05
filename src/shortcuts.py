"""Follow Windows .lnk shortcuts, which is how Google Drive shows a shared folder added to My Drive.

TODO(macOS): untested on a Mac. Real symlinks already work (Path.is_dir() follows them), but a
Finder alias is a different file format that this does not follow. Check with `ls -l` how Drive
for Desktop shows a folder shortcut there; if it is an alias, resolve it here (e.g. via osascript).
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

_HAS_TARGET_ID_LIST = 0x01
_HAS_LINK_INFO = 0x02


def read_lnk(path: Path) -> Path | None:
    """Local target of a .lnk file, or None if it isn't readable or isn't a local path."""
    try:
        data = path.read_bytes()
        if len(data) < 0x4C or struct.unpack_from("<I", data, 0)[0] != 0x4C:
            return None
        flags = struct.unpack_from("<I", data, 0x14)[0]
        pos = 0x4C
        if flags & _HAS_TARGET_ID_LIST:
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        if not flags & _HAS_LINK_INFO:
            return None
        info = pos
        header_size, info_flags, _, base_off = struct.unpack_from("<IIII", data, info + 4)
        if not info_flags & 0x01:  # no local base path (network target)
            return None
        suffix_off = struct.unpack_from("<I", data, info + 24)[0]
        if header_size >= 0x24:
            base = _wstr(data, info + struct.unpack_from("<I", data, info + 28)[0])
            suffix = _wstr(data, info + struct.unpack_from("<I", data, info + 32)[0]) if suffix_off else ""
        else:
            base = _astr(data, info + base_off)
            suffix = _astr(data, info + suffix_off) if suffix_off else ""
        target = Path(base) / suffix if suffix else Path(base)
        return target if base else None
    except (OSError, struct.error):
        return None


def _astr(data: bytes, off: int) -> str:
    return data[off:data.index(b"\0", off)].decode("mbcs" if sys.platform == "win32" else "latin-1")


def _wstr(data: bytes, off: int) -> str:
    end = off
    while data[end:end + 2] != b"\0\0":
        end += 2
    return data[off:end].decode("utf-16-le")


def follow(path: Path, looks_right=lambda p: (p / "people").is_dir() or (p / "media").is_dir()) -> Path:
    """`path` itself if it's a folder that already looks right, else where a shortcut leads.

    Handles a .lnk file given directly, and a folder that holds only a shortcut to the real
    folder (a Drive shortcut added to My Drive).
    """
    if path.is_file() and path.suffix.lower() == ".lnk":
        target = read_lnk(path)
        return target if target and target.is_dir() else path
    if path.is_dir() and not looks_right(path):
        targets = [t for lnk in path.glob("*.lnk") if (t := read_lnk(lnk)) and t.is_dir() and looks_right(t)]
        if len(targets) == 1:
            return targets[0]
    return path
