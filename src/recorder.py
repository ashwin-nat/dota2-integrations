import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

RECORDINGS_DIR = Path("recordings")


class Recorder:
    """Keeps every incoming GSI payload in memory until `save()` writes them as JSONL."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

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
        logger.info(f"Saved {len(self._entries)} payloads to {path}")
        return path
