---
name: dota-permanent-buff
description: Add a permanent buff (a stack counter the hero keeps, like Tidehunter's Leviathan's Catch or Muerta's Supernatural) to the Soundbo editor's "Permanent buffs" tab, so rules can trigger when its stacks go up or down. Use when the user says things like "track this permanent buff", "add the Bounty Hunter track gold stacks", "play a sound when my buff stacks go up". It is a data change in permanent_buffs.json, with no engine code. Not for a new kind of trigger (use dota-monitor) or for writing rules (use dota-rules).
---

# Adding a permanent buff

The backend `hero_buff` monitor takes any modifier name, so a new buff is **one entry in `src/config_ui/static/permanent_buffs.json`**. No Python, no `app.js` change. The editor builds the "Permanent buffs" tab from that file: one icon per entry, with a "Stack gained" tab and, for `bidirectional` buffs, a "Stack lost" tab.

## 1. Look the buff up in the catalog cache first

Before you ask for a recording or read logs, read `.cache/catalog.json`. It is the dotaconstants data the editor already uses (`src/config_ui/catalog.py` fetches it and refreshes it when the game version changes), so it is on disk and needs no network:

```
python -I -c "import json,sys; c=json.load(open('.cache/catalog.json',encoding='utf-8')); q=sys.argv[1].lower(); [print(h['key'], a['key'], '|', a['name'], '|', a['desc']) for h in c['heroes'] for a in h['abilities'] if q in (h['key']+' '+h['name']+' '+a['key']+' '+a['name']+' '+a['desc']).lower()]" "<hero, ability or word>"
```

From it, take:

- **The hero and ability keys**, for `icon` (e.g. `ability:tidehunter_leviathans_catch`). If no ability fits (a talent, a facet, an item effect), use the hero key: `hero:<key>`. An ability being in the cache does **not** mean Valve's CDN has its image: newer innates often have none (`silencer_brain_drain`, `rattletrap_armor_power`). Step 3 checks this.
- **The ability's in-game text**, for `description` and `tooltip`.
- **What the text says about the stacks** ("permanently", "loses half on death", and so on). This is your first reading of `kind`.

Tell the user what you found and the cache's `game_version`. If the hero or ability isn't there, or the file is missing, say so; starting the app or opening the editor refreshes the cache.

The cache does **not** have the modifier key, and the key often doesn't match the ability name (Clockwerk's Armor Power is `modifier_rattletrap_junk_mail`). So you still need step 2 to get the key and confirm the stacks really count, but you go in knowing what to look for.

Present list of choices to user if Claude is unsure.

## 2. Find the modifier and how it behaves

The user's required input is a recording of a hero that has the buff, or at least its modifier name. Don't guess either from memory of how GSI looks.

```
uv run python tools/frames.py recordings/<file>.jsonl --path hero.permanent_buffs
```

This prints one row per frame where the buffs changed. From it, work out:

- **The modifier name**: the key in `hero.permanent_buffs` (e.g. `modifier_muerta_supernatural`).
- **Is it a counter?** `{"stack_count": N}` with N changing is a counter. A presence flag (always 0, like `modifier_item_aghanims_shard`) has no stacks to trigger on; tell the user and stop (`hero_bool` already covers shard and scepter).
- **Is it permanent?** A key that comes and goes while the same hero is in play is a timed buff, not a permanent one; don't add those. A key that vanishes along with all the hero's other data (a hero swap in demo mode, a new match) says nothing, so check the hero name in the same frames. `modifier_pudge_innate_graft_flesh` was once wrongly called timed here; a full recording showed it kept 11 stacks through five deaths.
- **`kind`**: `monotonic` if the count only ever rises in the recording (and by the game's rules: the ability text from step 1), `bidirectional` if it can also fall. A recording alone can show a drop but never prove there isn't one, so check the ability's description too and ask the user if unsure. If the buff only grows, a "Stack lost" tab would never fire, so don't offer one.
- A key may be absent before the first stack (Leviathan's Catch) or present at 0 (Muerta); both work, the monitor counts absent as 0.
- Frames arrive about 1 s apart, so a quick run of gains fires once, and a step bigger than 1 (Bounty Hunter's +40) is still one gain.

If the recording doesn't contain the buff, say so and ask for one; don't invent a modifier name.

## 3. Add the entry

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
- `icon`: `ability:<name>`, `item:<name>` or `hero:<name>`. Use the ability when there is one. When the buff has no ability icon (a talent, a facet, an item effect), use `hero:<hero key>`, e.g. `hero:bounty_hunter`. You have the name from step 1; for an item, item keys are under `items` in the same file. The name must match the CDN image name exactly, and **there is no fallback**: a missing image is a 404 HTML page, shown as a broken icon (Firefox logs "A resource is blocked by OpaqueResponseBlocking"). Before writing the entry, check the image exists:

  ```
  curl -s -o /dev/null -w '%{http_code} %{content_type}\n' https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/abilities/<name>.png
  ```

  (`items/` or `heroes/` for the other sources.) Anything but `200 image/png` means that icon can't be used. Don't guess other spellings. Use `hero:<hero key>` and tell the user the ability has no CDN image (Clockwerk's Armor Power and Silencer's Suffer In Silence both use this). To see what a hero's abilities are actually called, Valve's datafeed lists them: `https://www.dota2.com/datafeed/herodata?language=english&hero_id=<id>` (`result.data.heroes[0].abilities[].name`, innates marked `ability_is_innate`).

Keep the file's two-space indentation and its trailing newline. The file is un-ignored in `.gitignore` (`*.json` is otherwise ignored), so check it appears in `git status`.

## 4. Check

1. `uv run pytest` (the file test runs with the suite; it checks fields, not icons).
2. **`uv run python tools/check_buff_icons.py` must print `all icons load` and exit 0.** It builds every entry's icon URL the way `app.js` does and fails on anything but a 200 image. A `FAIL` line is a blocker: fix the icon (step 3) and run it again. Don't hand off with a failing icon, and don't skip this because the curl in step 3 passed. It checks the whole file, so it also catches older entries whose image Valve has since removed. It needs the network; if it can't reach the CDN, say so in the hand-off rather than calling the icons checked.
3. Open the editor (`uv run python -m src.main --no-browser`, volume 0, `/ui`), go to Permanent buffs, and confirm the new icon shows (not a broken image), its tooltip, and the tabs: one for `monotonic`, two for `bidirectional`.
4. Optionally prove the trigger against the recording: add a rule with a harmless light action (rules with no enabled actions are skipped) and replay it with the `dota-replay` skill, then compare the fired rows in `logs/dota2-integrations.log` with the `frames.py` table.

If a buff misbehaves in a way a generic stack counter can't handle, don't special-case it in the data file; that is a `dota-monitor` change (and a "Why its own class:" note).

## 5. Hand-off

Show the user the new JSON entry and say what the recording showed (which frames the stacks changed in, and the reasoning for `kind`). Include the `check_buff_icons.py` result. If the icon is `hero:` because the ability has no CDN image, say so. Mention anything unverified: no recording of the buff dropping, an icon not yet seen in the editor, and so on. Then stop and let them review. **Do not commit until they explicitly approve**, on the current branch, with no push and no attribution trailers.

## What the rule looks like

For reference, the `rules.json` monitor block the editor writes (no `kind`; that lives only in the data file):

```json
{ "type": "hero_buff", "buff": "modifier_muerta_supernatural", "event": "STACK_LOST" }
```

`event` is `STACK_GAINED` or `STACK_LOST`. Existing rules for a buff that is later removed from the data file keep working in the engine and appear under "Other" in the tab.
