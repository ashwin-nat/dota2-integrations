import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH = Path("logs/dota2-integrations.log")


def setup_logging(
    path: Path = LOG_PATH,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """Configure the root logger to write to stdout and a rotating log file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    file_handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(stdout_handler)
    root.addHandler(file_handler)

    # aiohttp logs every request at INFO; GSI posts several times a second
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
