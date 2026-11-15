"""Print how one ability, item, hero block or dotted path changes across a recording.

    uv run python tools/frames.py recordings/x.jsonl --list
    uv run python tools/frames.py recordings/x.jsonl --ability sniper_shrapnel
    uv run python tools/frames.py recordings/x.jsonl --item item_blink --context 2
    uv run python tools/frames.py recordings/x.jsonl --slot abilities.ability3
    uv run python tools/frames.py recordings/x.jsonl --hero
    uv run python tools/frames.py recordings/x.jsonl --path map.paused

Reads the JSONL written by `--record` (`{"ts", "data"}` per line). One row per frame where the
block's values changed (plus the first and last), with the frame index and `map.clock_time`; the
whole payload is never printed. Use `--context N` to also show N frames each side of a change,
and `--all` for every frame. A block that is missing shows `(absent)`; for an ability or item the
slot it sits in is shown first, so a slot shift (Invoker) or an in-place transform (Centaur) is
visible. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Vary every frame without meaning anything, or echo the old values of what changed.
NOISY_KEYS = {"xpos", "ypos", "xp", "gold", "gold_reliable", "gold_unreliable", "previously", "added"}
ABSENT = "(absent)"


def load(path: Path) -> list[dict]:
    frames = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"{path}:{n}: not JSON ({e})")
            frames.append(entry)
    return frames


def get_path(data: dict, dotted: str):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def find_named(data: dict, section: str, name: str) -> tuple[str | None, dict | None]:
    """The slot id and block of the ability/item called `name`, or (None, None)."""
    for slot, block in (data.get(section) or {}).items():
        if isinstance(block, dict) and block.get("name") == name:
            return slot, block
    return None, None


def list_names(frames: list[dict]) -> None:
    seen: dict[str, dict[str, set[str]]] = {"abilities": {}, "items": {}}
    heroes: set[str] = set()
    for entry in frames:
        data = entry.get("data") or {}
        for section in seen:
            for slot, block in (data.get(section) or {}).items():
                if isinstance(block, dict) and block.get("name") and block["name"] != "empty":
                    seen[section].setdefault(block["name"], set()).add(slot)
        hero = (data.get("hero") or {}).get("name")
        if hero:
            heroes.add(hero)
    print("heroes:", ", ".join(sorted(heroes)) or "-")
    for section, names in seen.items():
        print(f"{section}:")
        for name in sorted(names):
            print(f"  {name}  ({', '.join(sorted(names[name]))})")


def select(data: dict, args: argparse.Namespace) -> tuple[str, object]:
    """(label for the slot or path, the block) for one frame."""
    if args.ability or args.item:
        section = "abilities" if args.ability else "items"
        slot, block = find_named(data, section, args.ability or args.item)
        return (slot or "-"), block
    if args.slot:
        return args.slot, get_path(data, args.slot)
    if args.hero:
        return "hero", data.get("hero")
    return args.path, get_path(data, args.path)


def comparable(block: object, ignore: set[str]) -> object:
    if isinstance(block, dict):
        return {k: v for k, v in block.items() if k not in ignore}
    return block


def show(block: object, ignore: set[str]) -> str:
    if block is None:
        return ABSENT
    if isinstance(block, dict):
        return " ".join(f"{k}={v}" for k, v in block.items() if k not in ignore)
    return str(block)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("recording", type=Path)
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--list", action="store_true", help="list the heroes, abilities and items in the recording")
    what.add_argument("--ability", help="ability name, e.g. sniper_shrapnel (followed wherever its slot is)")
    what.add_argument("--item", help="item name, e.g. item_blink")
    what.add_argument("--slot", help="follow one slot whatever sits in it, e.g. abilities.ability3 or items.slot0")
    what.add_argument("--hero", action="store_true", help="the hero block")
    what.add_argument("--path", help="any dotted path, e.g. map.paused or player.kills")
    p.add_argument("--context", type=int, default=0, metavar="N", help="also show N frames either side of a change")
    p.add_argument("--all", action="store_true", help="show every frame, not only changes")
    p.add_argument("--fields", help="comma-separated fields to show (default: all but position/gold noise)")
    p.add_argument("--keep-noise", action="store_true", help="do not hide position, xp and gold fields")
    p.add_argument("--from", dest="start", type=float, help="first clock_time to show")
    p.add_argument("--to", dest="end", type=float, help="last clock_time to show")
    args = p.parse_args()

    frames = load(args.recording)
    if not frames:
        sys.exit("empty recording")
    if args.list:
        list_names(frames)
        return

    ignore = set() if args.keep_noise else set(NOISY_KEYS)
    wanted = set(args.fields.split(",")) if args.fields else None

    def project(block: object) -> object:
        if wanted and isinstance(block, dict):
            return {k: v for k, v in block.items() if k in wanted}
        return comparable(block, ignore)

    rows = []
    for i, entry in enumerate(frames):
        data = entry.get("data") or {}
        clock = get_path(data, "map.clock_time")
        slot, block = select(data, args)
        rows.append((i, clock, slot, project(block), entry.get("note")))

    changed = {0, len(rows) - 1}
    for i in range(1, len(rows)):
        if rows[i][2:4] != rows[i - 1][2:4] or rows[i][4]:
            changed.add(i)
    if args.all:
        shown = set(range(len(rows)))
    else:
        shown = set()
        for i in changed:
            shown.update(range(max(0, i - args.context), min(len(rows), i + args.context + 1)))

    if all(r[3] is None for r in rows):
        print(f"{ABSENT} in every frame; try --list to see the names in this recording", file=sys.stderr)

    last = None
    for i, clock, slot, block, note in rows:
        if i not in shown:
            continue
        if clock is not None and ((args.start is not None and clock < args.start) or (args.end is not None and clock > args.end)):
            continue
        if last is not None and i != last + 1:
            print("  ...")
        last = i
        mark = "*" if i in changed else " "
        text = f"{mark} #{i:<5} t={clock if clock is not None else '?':>6}  [{slot}] {show(block, set())}"
        if note:
            text += f"   NOTE: {note}"
        print(text)


if __name__ == "__main__":
    main()
