---
name: dota-permanent-buff
description: Add a permanent buff (a stack counter the hero keeps, like Tidehunter's Leviathan's Catch or Muerta's Supernatural) to the Soundbo editor's "Permanent buffs" tab, so rules can trigger when its stacks go up or down. Use when the user says things like "track this permanent buff", "add the Bounty Hunter track gold stacks", "play a sound when my buff stacks go up". It is a data change in permanent_buffs.json, with no engine code. Not for a new kind of trigger (use dota-monitor) or for writing rules (use dota-rules).
---

# Adding a permanent buff

The backend `hero_buff` monitor takes any modifier name, so a new buff is **one entry in `src/config_ui/static/permanent_buffs.json`**. No Python, no `app.js` change. The editor builds the "Permanent buffs" tab from that file: one icon per entry, with a "Stack gained" tab and, for `bidirectional` buffs, a "Stack lost" tab.

## 1. Find the modifier and how it behaves

The user's required input is a recording of a hero that has the buff, or at least its modifier name. Don't guess either from memory of how GSI looks.

```
uv run python tools/frames.py recordings/<file>.jsonl --path hero.permanent_buffs
```

This prints one row per frame where the buffs changed. From it, work out:

- **The modifier name**: the key in `hero.permanent_buffs` (e.g. `modifier_muerta_supernatural`).
- **Is it a counter?** `{"stack_count": N}` with N changing is a counter. A presence flag (always 0, like `modifier_item_aghanims_shard`) has no stacks to trigger on; tell the user and stop (`hero_bool` already covers shard and scepter).
- **Is it permanent?** `modifier_pudge_innate_graft_flesh` showed up and vanished within a minute; that is a timed buff, not a permanent one. Don't add those.
- **`kind`**: `monotonic` if the count only ever rises in the recording (and by the game's rules: check the ability text), `bidirectional` if it can also fall. A recording alone can show a drop but never prove there isn't one, so check the ability's description too and ask the user if unsure. If the buff only grows, a "Stack lost" tab would never fire, so don't offer one.
- A key may be absent before the first stack (Leviathan's Catch) or present at 0 (Muerta); both work, the monitor counts absent as 0.
- Frames arrive about 1 s apart, so a quick run of gains fires once, and a step bigger than 1 (Bounty Hunter's +40) is still one gain.

If the recording doesn't contain the buff, say so and ask for one; don't invent a modifier name.

## 2. Add the entry

Append an object to the array in `src/config_ui/static/permanent_buffs.json`, with all six fields (`tests/test_permanent_buffs_file.py` rejects a missing or empty one, an unknown `kind`, a key without the `modifier_` prefix, or a duplicate key):

```json
{
  "key": "modifier_bounty_hunter_track_gold",
  "name": "Track gold",
  "tooltip": "Bounty Hunter's gold stolen with Track.",
  "description": "Longer text shown in the inspector: what the buff is and how its stacks change.",
  "kind": "monotonic",
  "icon": "ability:bounty_hunter_track"
}
```

- `key`: the modifier name, exactly as in the recording.
- `name`: the display name, on the inspector header and in the rules list ("Track gold · Stack gained").
- `tooltip`: one short line, shown in the hover tooltip on the grid icon.
- `description`: the fuller text shown under the title in the inspector. Take it from the ability's in-game text.
- `kind`: `monotonic` or `bidirectional` (see above).
- `icon`: `ability:<name>`, `item:<name>` or `hero:<name>`. Use the ability when there is one. When the buff has no ability icon (a talent, a facet, an item effect), use `hero:<hero key>`, e.g. `hero:bounty_hunter`. The name must match the CDN image name exactly, and a wrong one shows a broken image, which the file test can't catch. Look it up in `.cache/catalog.json` (ability keys under each hero's `abilities`, hero keys under `heroes`, item keys under `items`).

Keep the file's two-space indentation and its trailing newline. The file is un-ignored in `.gitignore` (`*.json` is otherwise ignored), so check it appears in `git status`.

## 3. Check

1. `uv run pytest` (the file test runs with the suite).
2. Open the editor (`uv run python -m src.main --no-browser`, volume 0, `/ui`), go to Permanent buffs, and confirm the new icon, its tooltip, and the tabs: one for `monotonic`, two for `bidirectional`.
3. Optionally prove the trigger against the recording: add a rule with a harmless light action (rules with no enabled actions are skipped) and replay it with the `dota-replay` skill, then compare the fired rows in `logs/dota2-integrations.log` with the `frames.py` table.

If a buff misbehaves in a way a generic stack counter can't handle, don't special-case it in the data file; that is a `dota-monitor` change (and a "Why its own class:" note).

## 4. Hand-off

Show the user the new JSON entry and say what the recording showed (which frames the stacks changed in, and the reasoning for `kind`). Mention anything unverified: no recording of the buff dropping, an icon name not yet seen in the editor, and so on. Then stop and let them review. **Do not commit until they explicitly approve**, on the current branch, with no push and no attribution trailers.

## What the rule looks like

For reference, the `rules.json` monitor block the editor writes (no `kind`; that lives only in the data file):

```json
{ "type": "hero_buff", "buff": "modifier_muerta_supernatural", "event": "STACK_LOST" }
```

`event` is `STACK_GAINED` or `STACK_LOST`. Existing rules for a buff that is later removed from the data file keep working in the engine and appear under "Other" in the tab.
