from __future__ import annotations

import re
from pathlib import Path

MEDIA_DIR = Path("media")
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg"}


def safe_filename(name: str) -> str:
    name = Path(name).name
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    stem = re.sub(r"[^\w\- ]+", "", stem).strip() or "clip"
    return f"{stem}{ext}"
