import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

RECORDINGS_DIR = Path("recordings")


def _file_name(name: str) -> str:
    stem = re.sub(r"[^\w\- ]+", "", Path(name).name.removesuffix(".jsonl")).strip()
    if not stem:
        raise ValueError("Use letters, numbers, spaces, - or _ in the name")
    return f"{stem}.jsonl"


class Recorder:
    """Keeps every incoming GSI payload in memory until `save()` writes them as JSONL."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def __len__(self) -> int:
        return len(self._entries)

    def record(self, data: dict) -> None:
        self._entries.append({"ts": datetime.now().astimezone().isoformat(), "data": data})

    def save(self, directory: Path = RECORDINGS_DIR, name: str | None = None) -> Path:
        """Write the history as JSONL, to `name` or a timestamped file. Raises ValueError if `name` can't be used."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / _file_name(name) if name else directory / f"gsi_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.jsonl"
        if name and path.exists():
            raise ValueError(f"{path.name} already exists")
        with path.open("w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry) + "\n")
        logger.info(f"Saved {len(self._entries)} payloads to {path}")
        return path
