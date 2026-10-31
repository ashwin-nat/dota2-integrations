# CLAUDE.md

## Project

Dota 2 GSI (Game State Integration) receiver. Accepts raw POST payloads from the Dota 2 client, holds the latest snapshot in memory, and drives a rule engine that triggers sound/lighting actions on game events.

## Tech Stack

- Python 3.13
- `asyncio` — async runtime
- `aiohttp` — HTTP server
- `pydantic` — rule/action config validation
- `uv` — dependency and environment management
- `yt-dlp` — fetches audio from video links for the soundboard
- `lameenc` — encodes soundboard clips to MP3

## Running

```bash
uv run python -m src.main
```

Listens on `http://127.0.0.1:6969` (override with the `GSI_PORT` env var). Dota 2 sends POST requests to `/`.

A browser rules editor ("Rule Forge") is served on the same port at `http://127.0.0.1:6969/ui`. Saving there validates with `RulesConfig`, writes `rules.json`, and hot-reloads the rules (`reload_rules` in `main.py`); only lighting vendor/enabled changes need a restart.

The editor's Soundboard tab (`src/config_ui/soundboard.py`) keeps clip details in `soundboard.json` and saves each change immediately instead of through the Save button. The browser decodes the source at 44.1 kHz and trims it to `MAX_CLIP_SECONDS` (5.2 s, as in Discord), then uploads a 16-bit WAV. The server encodes it to MP3 with `lameenc` as `media/<clip name>.mp3`, so clips appear in the rule sound pickers. Renaming a clip renames the file and rewrites matching `play_sound` actions in `rules.json`; deleting it disables them (`retarget_rules`). On startup, clips from the first version (WAVs in `media/soundboard/`) are converted. Links are fetched server-side with yt-dlp (`POST /api/soundboard/fetch`, audio only, no ffmpeg needed), and the raw audio is returned for trimming in the browser.

Requires `lighting_config_{vendor}.json` (e.g. `lighting_config_tapo.json`, auto-created on first run) and an optional `rules.json` in the project root.

## Project Structure

```
src/
├── main.py                    # entry point — wires all subsystems, runs asyncio tasks
├── ingress/
│   └── http_server.py         # POST / handler (logs and strips a top-level `note` field if present), GET /state debug dump, /record/save in record mode
├── state/
│   ├── store.py               # GameState — snapshot store, drives rule monitors on every update
│   ├── items.py               # Items / item type parsing (EmptyItem, NoChargeItem, SingleChargeItem, MultiChargeItem)
│   ├── abilities.py           # Abilities / Ability — one dataclass for every ability slot
│   └── map.py                 # MapState parsing
├── events/
│   ├── bus.py                 # EventBus — async fan-out bus for internal events
│   └── codes.py               # EventCode enum
├── rules/
│   ├── config.py              # Pydantic models: Rule, AnyMonitor, AnyAction, RulesConfig
│   ├── compiler.py            # compile_rules() — builds CompiledRules from RulesConfig
│   ├── bus.py                 # RuleEventBus — string-key async queue bus for rule events
│   ├── action_executor.py     # ActionExecutor — dispatches typed actions to sound/lighting
│   ├── item_monitors.py       # ItemMonitor subclasses + ITEM_MONITOR_REGISTRY / MIDAS_MONITOR_REGISTRY
│   ├── ability_monitors.py    # AbilityMonitor + ABILITY_MONITOR_REGISTRY (cooldown-started tracking)
│   └── map_monitor.py         # MapMonitor — day/night cycle transition detector
├── recorder.py                # Recorder — keeps payloads in memory for --record, saves JSONL
├── monitors/
│   ├── base.py                # Monitor ABC
│   └── day_night.py           # Legacy day/night monitor (pre-rule-engine)
├── config_ui/
│   ├── routes.py              # /ui editor + /api (config get/put, media list/upload, play, catalog)
│   ├── catalog.py             # hero/ability/item names from dotaconstants, cached in .cache/catalog.json
│   ├── soundboard.py          # soundboard clips API (create/edit/delete/play, link fetch via yt-dlp)
│   ├── files.py               # media/ dir, allowed audio extensions, safe_filename()
│   └── static/                # index.html, app.js, app.css (vanilla, no build step)
├── lighting/
│   └── controller.py          # LightingController — Philips Hue RGB control
└── sound/
    └── manager.py             # SoundManager — async audio playback
```

## Key Design Decisions

- **No schema assumptions on raw state** — GSI payload is stored as an opaque `dict`; typed state (`Items`, `MapState`) is parsed alongside it.
- **Latest snapshot wins** — each `state.update(data)` fully replaces the previous state.
- **Transport-agnostic state layer** — `GameState` has no aiohttp dependency.
- **Type-safe handler injection** — HTTP handler receives `EventBus` as a bound arg, emits `INCOMING_DATA`; `GameState` subscribes to that event.
- **No locks** — single writer (HTTP handler via event bus), multiple readers allowed.
- **Rule engine is compiled at startup** — `compile_rules()` parses `rules.json` once into `CompiledRules` (lists of monitor instances pre-wired to `RuleEventBus`). No runtime routing logic.
- **Two async buses** — `EventBus` for internal infrastructure events; `RuleEventBus` for string-key rule events dispatched to `ActionExecutor`.

## State API (`src/state/store.py`)

```python
GameState(compiled_rules, rule_bus, light_arbiter)  # all required, wired once at startup
state.update(data)               # -> None              replace snapshot, run rule monitors
state.version()                  # -> int               monotonic counter, increments on every set
state.items                      # -> Items | None       parsed item slots
state.abilities                  # -> Abilities | None   parsed ability slots (ability0..abilityN)
state.map                        # -> MapState | None    parsed map state
```

## Rule Engine (`src/rules/`)

Rules are loaded from `rules.json` (array of `Rule` objects) and compiled once at startup.

### Monitor types

| `type`   | Config model         | Events                                          |
|----------|----------------------|-------------------------------------------------|
| `item`   | `ItemMonitorConfig`  | `COOLDOWN_READY`, `COOLDOWN_STARTED`, `ITEM_ACQUIRED`, `ITEM_LOST` |
| `midas`  | `MidasMonitorConfig` | `CHARGED` (0→1 charge), `OVERCHARGED` (→2 charges) |
| `map`    | `MapMonitorConfig`   | `DAYTIME_STARTED`, `NIGHTTIME_STARTED`          |
| `ability`| `AbilityMonitorConfig` | `COOLDOWN_STARTED` (cooldown 0 → > 0)         |

`ability` monitors take a `target` — the internal ability name from the GSI `abilities` block (e.g. `spectre_reality`), so no ability list is maintained in code. They only track learned abilities (`level > 0`) and ignore `max_cooldown` (the game reports it unreliably). Choosing an ability that actually has a cooldown is the rule author's responsibility.

### Action types

| `type`         | Fields                  | Notes                                      |
|----------------|-------------------------|--------------------------------------------|
| `play_sound`   | `file: str`             |                                            |
| `light`        | `r`, `g`, `b` (0–255)  |                                            |
| `reset_light`  | _(none)_                | Restores day/night colour from `map_colours`; forbidden on map monitors |

### `rules.json` format

`rules.json` can be either a plain array (legacy) or an object with a `rules` key and optional `map_colours`:

```json
{
  "map_colours": {
    "day":   { "r": 255, "g": 220, "b": 100 },
    "night": { "r":  30, "g":  30, "b": 100 }
  },
  "rules": [
    {
      "id": "midas-overcharged",
      "monitor": { "type": "midas", "event": "OVERCHARGED" },
      "actions": [{ "type": "light", "r": 255, "g": 180, "b": 0 }]
    },
    {
      "id": "midas-charged",
      "monitor": { "type": "midas", "event": "CHARGED" },
      "actions": [{ "type": "reset_light" }]
    }
  ]
}
```

`map_colours` is required when any rule uses `reset_light`. The plain array format remains supported for configs that don't use `reset_light`.

Ability monitors follow an ability that transforms in place (Centaur's `centaur_work_horse` becomes `centaur_mount` in the same slot while active): they remember the target's slot, and the target's name vanishing from a slot while it was ready counts as the cooldown starting (fired once; the later revert does not fire again).

## Record, replay and debugging

`uv run python -m src.main --record` keeps every payload in memory; `GET /record/save` writes `recordings/gsi_*.jsonl` (`{"ts", "data"}` per line, optional `"note"`). `tools/replay.py <file>` POSTs a recording to a running app (`--speed`, `--instant`), and `--step` is an interactive stepper (next N frames, run to next change, diff, state dump, fired rules, `note` to annotate). Notes live in `<file>.notes.json` keyed by `ts` and are injected into the POSTed JSON as a top-level `note`, which the app logs and strips. `GET /state` returns `{version, raw, fired}` after draining the ingest queue; `GameState.raw` and `RuleEventBus.drain_fired()` exist for it. See the `dota-replay` skill (`.agents/skills/dota-replay/`) for the workflow. When a monitor misbehaves, reproduce it from a recording and inspect the per-frame diff first; the skill has a debugging checklist. Rules with no enabled actions are skipped at compile time, so use a harmless action (e.g. a light) when reproducing a bug.

## Build & Release

```bash
uv run pyinstaller --onefile --paths . --name dota2-integrations \
  --add-data "src/config_ui/static:src/config_ui/static" src/main.py   # -> dist/dota2-integrations.exe
```

The `--add-data` is required: without the editor's static files the server crashes on startup. On startup the app opens the editor (`/ui`) in the default browser; pass `--no-browser` or set `GSI_NO_BROWSER=1` to skip that. The editor's power button (`POST /api/shutdown`) sets the stop event in `main()`, which cancels every task so the port is closed before the process exits.

`.github/workflows/build.yml` (manual) builds Windows (`.exe`) and macOS (`.app` for Apple Silicon and Intel, zipped with `ditto` so the bundle's symlinks and signature survive) from the current code as workflow artifacts. `release.yml` (manual, takes a tag) reuses it and publishes a GitHub release with the binaries plus `rules.example.json` (shipped as `rules.json`: no sounds, lighting disabled, empty actions) and a zip of `.agents/skills`. The Windows exe reads `rules.json`, `lighting_config_*.json`, `logs/` and sound files from the directory it's run in; the macOS .app uses `~/Library/Application Support/dota2-integrations/` (it has no console).
