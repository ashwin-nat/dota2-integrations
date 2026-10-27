---
name: dota-rules
description: Add, edit, remove, or debug rules in rules.json for the dota2-integrations app — triggers (item/ability cooldowns, item bought/lost, Midas charges, day/night, pause, hero death/respawn) mapped to actions (play sound, set light colour, call webhook). Use when the user says things like "play X when I use BKB", "turn the light red when I die", "why didn't my rule fire". Not for first-time install or lighting device setup (use dota-setup).
---

# dota2-integrations rules

`rules.json` in the project root holds `rules`, `sound` and `lighting`. The schema source of truth is `src/rules/config.py`. Read it before every edit, because monitor types, events and action fields change over time. Don't rely on schema tables in project docs or agent instruction files; they lag behind the code.

## Rule shape

```json
{
  "id": "bkb_used",
  "monitor": { "type": "item", "target": "item_black_king_bar", "event": "COOLDOWN_STARTED" },
  "actions": [
    { "type": "play_sound", "file": "media/piles.mp3", "volume": 25 },
    { "type": "light", "r": 200, "g": 0, "b": 0, "priority": 3 }
  ]
}
```

Every action has `enabled` (default `true`). Use it to switch an action off without deleting it.

## Translating a request into a rule

1. **Pick the monitor.** Map the user's wording to a `type` + `event` in `config.py`. Things to know:
   - `blink` is a shortcut for `item` with `target: "item_blink"`; both use the same blink-specific logic, which ignores the 3s damage-cancel cooldown.
   - `midas` events are about charges (`CHARGED` = 1 charge, `OVERCHARGED` = 2).
   - `item` COOLDOWN_STARTED on `item_black_king_bar` is special-cased: it stays active only for the ~10s buff window, not the full cooldown.
   - `ability` only supports `COOLDOWN_STARTED`, and only for learned abilities. If the user asks about an ability with no cooldown (most passives), tell them the rule will never fire.
2. **Resolve the `target` key.** It is the internal game name, not the display name. Never guess it.
   - **Items:** look the key up in the item table on https://dota2.fandom.com/wiki/Cheats. Fetch the page's raw wikitext into a temp directory outside the repo. The rendered HTML page is too large to read reliably.
     ```
     curl -sS -A Mozilla/5.0 -o <tmpdir>/cheats.json "https://dota2.fandom.com/api.php?action=parse&page=Cheats&prop=wikitext&format=json"
     ```
     Then pull out display name → key pairs:
     ```
     python -I -c "import json,re,sys; w=json.load(open(sys.argv[1],encoding='utf-8'))['parse']['wikitext']['*']; [print(a,'\t',b) for a,b in re.findall(r'\{\{I\|([^}|]+)[^}]*\}\}\s*\n\|\s*<code>(item_\w+)</code>',w)]" <tmpdir>/cheats.json
     ```
     Match the user's item to a display name; abbreviations like "BKB", "aghs", "euls" are fine to resolve. Keys often differ from display names: Aghanim's Scepter → `item_ultimate_scepter`, Eul's → `item_cyclone`, Battle Fury → `item_bfury`. If several entries could match (e.g. Aghanim's Scepter vs Blessing), ask which one. Use the item key, not the `item_recipe_*` column.
   - **Abilities:** no complete list is published online, and the set is too large to keep in this repo. Instead, the app writes the player hero's ability keys to the log at the start of each match, under a `Hero abilities:` line.
     1. Grep `logs/dota2-integrations.log*` (the log rotates, so include the backups) for `Hero abilities:` and read the names listed under each match. Keys look like `<hero>_<ability>`, e.g. `spectre_reality`.
     2. If the exact key is there, use it.
     3. If not, don't guess. Ask the user to start the app, open demo mode with that hero **as their own hero** (GSI only reports the player's hero, not allies or enemies), wait for the match to load, then come back. Then grep the log again for the exact key.
3. **Pick the actions.** The field-by-field details are in `config.py`. Notes per action:
   - `play_sound`: `file` must exist on disk, relative to the project root, when the action is enabled; the app refuses to start otherwise. A disabled action may name a clip that isn't there yet (the editor at `/ui` lists these under Sounds → Wanted). List `media/` and suggest existing files before inventing a path. `volume` is per action (0-100) and is scaled by the global `sound.volume`.
   - `light`: see the priority rules below.
   - `webhook`: `url` must be http(s). If you set `api_key`, also set `auth_type` (`bearer` / `header` / `query`). `cooldown` is in seconds and stops repeated calls.
4. **Pick an `id`**: snake_case, unique, describing the trigger (e.g. `blink_used`, `hero_killed`).

## Light priorities and how long a colour lasts

Read this before adding any `light` action.

- **Map rules** (day/night) set the baseline colour. Their light actions must have `priority: null`.
- **Every other light action needs a `priority` ≥ 1 that is unique across all rules.** The highest active priority wins. List the priorities already in use and ask where the new one should rank, e.g. "should dying override the Midas glow?"
- **A colour lasts as long as the state it signals, not just a moment.** It is withdrawn when that state ends:
  - `COOLDOWN_STARTED`: while the item/ability is on cooldown (BKB: only the buff window)
  - `COOLDOWN_READY`: while it's off cooldown, i.e. most of the time
  - `ITEM_ACQUIRED`: **as long as the item is held**, so likely all game
  - `ITEM_LOST`: until the item comes back
  - `CHARGED` / `OVERCHARGED`: while Midas has that many charges
  - `HERO_KILLED`: while dead; `HERO_RESPAWNED`: while alive, i.e. most of the time
  
  When a rule's timing would keep a colour on for a long time (ITEM_ACQUIRED, COOLDOWN_READY, HERO_RESPAWNED), point this out before adding it. A sound-only rule is often what the user actually wants.
- `PAUSED` / `UNPAUSED` are map events, so a light on them replaces the baseline until the next day/night change. Warn the user about that.

## Other things to check

- **One rule per trigger.** Two rules with the same monitor (`type` + `target` + `event`) make each action fire twice. Add actions to the existing rule instead of creating a second one.
- A rule whose actions are all disabled, or that has no actions, is skipped at startup. That is a fine way to keep a placeholder.
- `blink` with event X and `item`/`item_blink` with the same event X are separate triggers, and both will fire. Don't create both.

## Editing and validating

1. Read `rules.json` and `src/rules/config.py`.
2. Show the user the rule you plan to add or change (as JSON) and any warnings from above, then edit the file. Keep the existing 4-space indent.
3. Validate:
   ```
   uv run python -c "from pathlib import Path; from src.rules import RulesConfig; c=RulesConfig.load(Path('rules.json')); print(len(c.rules),'rules ok')"
   ```
   Loading rewrites `rules.json` with default values filled in (`enabled`, `volume`, `priority: null`). That diff is expected.
4. Rules are compiled once at startup, so tell the user to restart the app.
5. Finish by showing **every** rule in `rules.json` (not just the changed ones) as a markdown table, one row per rule, in file order:

   | Rule | Trigger | Sound | Light | Webhook |
   |---|---|---|---|---|
   | `bkb_used` | Black King Bar used (`item_black_king_bar`) | `piles.mp3` @ 25% | 🟥 (200, 0, 0) · prio 3 | — |
   | `daytime_started` | Day starts | `wow.mp3` @ 25% | (255, 220, 100) · baseline | — |
   | `blink_ready` | Blink Dagger off cooldown | — | — | — |

   - Trigger: plain English (e.g. "BKB used", "Hero dies", "Midas at 2 charges"), with the raw `target` key in backticks for item and ability rules.
   - Sound: file name without the `media/` prefix, plus the volume.
   - Light: RGB value, plus `prio N`, or `baseline` for map rules. A rough colour emoji is optional.
   - Disabled actions: show them struck through (`~~piles.mp3~~`).
   - Rules with no enabled actions: show `—` in every action column.
   - Mark rows added or changed in this session with **bold** ids.

   Under the table, list the light priorities in use, highest first, so the user can see which colour wins when two are active.

## Debugging "my rule didn't fire"

Check in this order:
1. Did validation pass? A bad sound path or duplicate priority stops the app from starting.
2. Is the `target` key right? Look it up again the same way as when adding a rule: the Cheats table for items, the `Hero abilities:` log line for abilities.
3. Was the match in progress? Updates are ignored outside `DOTA_GAMERULES_STATE_GAME_IN_PROGRESS`, which includes the pre-horn strategy phase.
4. Grep `logs/dota2-integrations.log` for the rule id. Every fired action is logged as `rule='<id>' ... -> play_sound` / `-> light (...)`. If it fired but the light didn't change, a higher-priority light was active at the time.
5. For an ability: was it learned (level > 0)?
