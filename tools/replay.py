"""Replay a recording made with `--record` against a running instance.

    uv run python tools/replay.py recordings/x.jsonl [--speed 2] [--instant] [--url URL]
    uv run python tools/replay.py recordings/x.jsonl --step        # interactive stepper

A frame can carry a `note`: inline in the jsonl line, or in the sidecar
`<recording>.notes.json` (written by the stepper's `note` command, keyed by the
frame's `ts`). It is injected into the POSTed JSON as a top-level `note`, which
the app logs and strips.
"""
import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiohttp

# Change every frame without meaning anything, so they would drown out the diff.
NOISY_PATHS = {"provider.timestamp", "map.game_time", "map.clock_time"}
NOISY_PREFIXES = ("previously.", "added.")  # GSI echoes the old values of whatever just changed

HELP = """\
  <enter> | n [N]   send the next N frames (default 1)
  c [prefix]        send frames until a field changes (optionally only under a path prefix,
                    e.g. abilities.ability3) or a rule fires
  d                 show what changed in the last step
  s [path]          dump the app's raw state (whole thing, or a dotted path such as abilities.ability3)
  note <text>       annotate the current frame (saved to the sidecar notes file)
  h                 this help
  q                 quit"""


# --- recordings -------------------------------------------------------------

@dataclass
class Frame:
    ts: str
    data: dict
    note: str | None = None

    @property
    def time(self) -> datetime:
        return datetime.fromisoformat(self.ts)


def notes_path(recording: Path) -> Path:
    return recording.with_suffix(".notes.json")


def load_notes(recording: Path) -> dict[str, str]:
    path = notes_path(recording)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_frames(recording: Path) -> list[Frame]:
    notes = load_notes(recording)
    with recording.open(encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    return [Frame(e["ts"], e["data"], e.get("note") or notes.get(e["ts"])) for e in entries]


# --- state diffing ----------------------------------------------------------

def flatten(value, prefix: str = "") -> dict[str, object]:
    """{"a": {"b": 1}} -> {"a.b": 1}"""
    if not isinstance(value, dict):
        return {prefix: value}
    flat: dict[str, object] = {}
    for key, child in value.items():
        flat.update(flatten(child, f"{prefix}.{key}" if prefix else key))
    return flat


def diff(old: dict | None, new: dict | None, prefix: str = "") -> list[str]:
    """One line per changed field, ignoring noise; `prefix` limits it to one subtree."""
    before, after = flatten(old or {}), flatten(new or {})
    lines = []
    for path in sorted(before.keys() | after.keys()):
        if path in NOISY_PATHS or path.startswith(NOISY_PREFIXES) or not path.startswith(prefix):
            continue
        if before.get(path) != after.get(path):
            lines.append(f"  {path}: {before.get(path, '<absent>')!r} -> {after.get(path, '<absent>')!r}")
    return lines


def lookup(raw: dict, dotted: str):
    node = raw
    for part in dotted.split("."):
        node = node[part]
    return node


# --- talking to the app -----------------------------------------------------

async def send(session: aiohttp.ClientSession, url: str, index: int, frame: Frame) -> None:
    payload = {**frame.data, "note": frame.note} if frame.note else frame.data
    async with session.post(url, json=payload) as resp:
        if resp.status != 200:
            print(f"#{index}: HTTP {resp.status}")


async def replay(recording: Path, url: str, speed: float, instant: bool) -> None:
    frames = load_frames(recording)
    print(f"Replaying {len(frames)} payloads to {url}")
    async with aiohttp.ClientSession() as session:
        prev: Frame | None = None
        for index, frame in enumerate(frames, 1):
            if prev is not None and not instant:
                await asyncio.sleep(max((frame.time - prev.time).total_seconds(), 0) / speed)
            await send(session, url, index, frame)
            prev = frame
    print("Done")


# --- interactive stepper ----------------------------------------------------

class Stepper:
    def __init__(self, recording: Path, url: str, session: aiohttp.ClientSession) -> None:
        self._recording = recording
        self._url = url
        self._state_url = url.rstrip("/") + "/state"
        self._session = session
        self._frames = load_frames(recording)
        self._pos = 0  # frames sent so far; the current frame is _frames[_pos - 1]
        self._raw: dict | None = None  # the app's raw state after the current frame
        self._last_diff: list[str] = []

    async def run(self) -> None:
        commands = {
            "": self._next, "n": self._next, "c": self._until_change, "d": self._show_diff,
            "s": self._show_state, "note": self._add_note, "h": self._help,
        }
        print(f"{len(self._frames)} frames loaded. Type h for help.")
        while True:
            try:
                line = (await asyncio.to_thread(input, "> ")).strip()
            except EOFError:
                return
            name, _, arg = line.partition(" ")
            if name == "q":
                return
            if name not in commands:
                print("Unknown command, h for help")
                continue
            try:
                await commands[name](arg.strip())
            except (KeyError, ValueError) as e:
                print(f"Error: {e!r}")

    async def _fetch_state(self) -> dict:
        async with self._session.get(self._state_url) as resp:
            return await resp.json()

    async def _send_next(self) -> tuple[dict | None, list[str]] | None:
        """Send one frame; returns (previous raw state, rule events fired), or None at the end."""
        if self._pos >= len(self._frames):
            print("End of recording")
            return None
        frame = self._frames[self._pos]
        self._pos += 1
        await send(self._session, self._url, self._pos, frame)

        snap = await self._fetch_state()
        old, self._raw = self._raw, snap["raw"]
        self._last_diff = diff(old, self._raw)
        if frame.note:
            print(f"#{self._pos} {frame.ts}  NOTE: {frame.note}")
        for event in snap["fired"]:
            print(f"#{self._pos} FIRED {event}")
        return old, snap["fired"]

    async def _next(self, arg: str) -> None:
        for _ in range(int(arg) if arg else 1):
            if await self._send_next() is None:
                return
        print(f"#{self._pos} {self._frames[self._pos - 1].ts}")

    async def _until_change(self, prefix: str) -> None:
        while (sent := await self._send_next()) is not None:
            old, fired = sent
            changes = diff(old, self._raw, prefix) if self._pos > 1 else []  # frame 1 diffs against nothing
            if changes or fired:
                print(f"#{self._pos} {self._frames[self._pos - 1].ts}")
                print("\n".join(changes))
                return

    async def _show_diff(self, _: str) -> None:
        print("\n".join(self._last_diff) or "  (no changes)")

    async def _show_state(self, path: str) -> None:
        raw = (await self._fetch_state())["raw"]
        print(json.dumps(lookup(raw, path) if path else raw, indent=2))

    async def _add_note(self, text: str) -> None:
        if self._pos == 0:
            print("Step to a frame first")
            return
        frame = self._frames[self._pos - 1]
        frame.note = text
        notes = load_notes(self._recording) | {frame.ts: text}
        notes_path(self._recording).write_text(json.dumps(notes, indent=2), encoding="utf-8")
        print(f"Saved note for #{self._pos} to {notes_path(self._recording)}")

    async def _help(self, _: str) -> None:
        print(HELP)


async def step(recording: Path, url: str) -> None:
    async with aiohttp.ClientSession() as session:
        await Stepper(recording, url, session).run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay a recorded GSI session")
    parser.add_argument("file", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:6969/")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier")
    parser.add_argument("--instant", action="store_true", help="send everything with no delay")
    parser.add_argument("--step", action="store_true", help="interactive stepper: send frames on demand, inspect state, annotate")
    args = parser.parse_args()
    if args.step:
        asyncio.run(step(args.file, args.url))
    else:
        asyncio.run(replay(args.file, args.url, args.speed, args.instant))
