import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

RECORDINGS_DIR = Path("recordings")


class Recorder:
    """Keeps every incoming GSI payload in memory until `save()` writes them as JSONL."""

    def __init__(self) -> None:
        self._entries: list[dict] = []
        self._saved: set[Path] = set()  # only files this session wrote can be renamed

    def __len__(self) -> int:
        return len(self._entries)

    def record(self, data: dict) -> None:
        self._entries.append({"ts": datetime.now().astimezone().isoformat(), "data": data})

    def save(self, directory: Path = RECORDINGS_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"gsi_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry) + "\n")
        self._saved.add(path)
        logger.info(f"Saved {len(self._entries)} payloads to {path}")
        return path

    def rename(self, old_name: str, new_name: str, directory: Path = RECORDINGS_DIR) -> Path:
        """Rename a recording saved this session. Raises ValueError if the new name can't be used."""
        old = directory / Path(old_name).name
        if old not in self._saved:
            raise ValueError("Only recordings saved since the app started can be renamed")
        stem = re.sub(r"[^\w\- ]+", "", Path(new_name).name.removesuffix(".jsonl")).strip()
        if not stem:
            raise ValueError("Use letters, numbers, spaces, - or _ in the name")
        new = directory / f"{stem}.jsonl"
        if new == old:
            return old
        if new.exists():
            raise ValueError(f"{new.name} already exists")
        old.rename(new)
        self._saved.discard(old)
        self._saved.add(new)
        logger.info(f"Renamed recording {old.name} -> {new.name}")
        return new
