"""Replay a recording made with `--record` against a running instance.

    uv run python tools/replay.py recordings/gsi_2026_10_31_12_00_00.jsonl [--speed 2] [--instant] [--url URL]
"""
import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

import aiohttp


def load(path: Path) -> list[tuple[datetime, dict]]:
    entries = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                entries.append((datetime.fromisoformat(entry["ts"]), entry["data"]))
    return entries


async def replay(path: Path, url: str, speed: float, instant: bool) -> None:
    entries = load(path)
    print(f"Replaying {len(entries)} payloads to {url}")
    async with aiohttp.ClientSession() as session:
        prev = None
        for i, (ts, data) in enumerate(entries, 1):
            if prev is not None and not instant:
                await asyncio.sleep(max((ts - prev).total_seconds(), 0) / speed)
            prev = ts
            async with session.post(url, json=data) as resp:
                if resp.status != 200:
                    print(f"#{i}: HTTP {resp.status}")
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay a recorded GSI session")
    parser.add_argument("file", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:6969/")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier")
    parser.add_argument("--instant", action="store_true", help="send everything with no delay")
    args = parser.parse_args()
    asyncio.run(replay(args.file, args.url, args.speed, args.instant))
