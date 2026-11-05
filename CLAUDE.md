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

Tests: `uv run pytest`.

Listens on `http://127.0.0.1:6969` (override with the `GSI_PORT` env var). Dota 2 sends POST requests to `/`.

A browser rules editor (formerly "Rule Forge"; the app is now called Soundbo) is served on the same port at `http://127.0.0.1:6969/ui`. Saving there validates with `RulesConfig`, writes `rules.json`, and hot-reloads the rules (`reload_rules` in `main.py`); only lighting vendor/enabled changes need a restart.

The editor's Soundboard tab (`src/config_ui/soundboard.py`) keeps clip details in `soundboard.json` and saves each change immediately instead of through the Save button. The browser decodes the source at 44.1 kHz and trims it to `MAX_CLIP_SECONDS` (5.2 s, as in Discord), then uploads a 16-bit WAV. The server encodes it to MP3 with `lameenc` as `media/<clip name>.mp3`, so clips appear in the rule sound pickers. Renaming a clip renames the file and rewrites matching `play_sound` actions in `rules.json`; deleting it disables them (`retarget_rules`). On startup, clips from the first version (WAVs in `media/soundboard/`) are converted. Links are fetched server-side with yt-dlp (`POST /api/soundboard/fetch`, audio only, no ffmpeg needed), and the raw audio is returned for trimming in the browser.

Sharing with friends (`src/sharing.py`, editor API in `src/config_ui/sharing_routes.py`): settings live in local `sharing.json` (folder, name, followed friends, a device id that stops two people publishing under one name). With a folder set, `media/<file>` references resolve to `<folder>/media/` through `src/media.py` (`resolve`, `media_dir`, `media_ref`); always store `media/<name>` in rules and clips, never a resolved path. `publish()` writes `<folder>/people/<name>.json` (rules without webhooks, plus soundboard clips) on startup, on each rules save and on each soundboard change. Followed friends' sound actions (no lights or webhooks) are compiled alongside your own rules as `<friend>/<rule id>`, but never stack: a trigger you already have a sound for keeps yours, and the first-followed friend wins among friends (`followed_rules(own_rules)`). `watch_friends` in `main.py` recompiles when a followed file's mtime changes. Joining or leaving a folder copies sounds with `_bring_media`, which renames a same-name-different-content file and rewrites rules.json and soundboard.json to match.

Sound packs (`src/packs.py`) are the no-install alternative: `export_pack` zips `pack.json` (rules without webhooks, plus soundboard clips) and the sounds they reference. `import_pack` unpacks into the media folder, renaming clashing sounds and recording `files` (original name to stored name) so a later update overwrites its own files instead of piling up copies. Packs are stored in `packs/<id>.json`, followed as `pack:<id>` in `sharing.json`, and re-downloaded from their `source` link every 30 minutes (`refresh_packs` in `main.py`). `download_url` turns Google Drive and Dropbox share links into direct downloads.

Admins and listeners: `packs.write_library` (run every 30 s by `publish_library` in `main.py` while a shared folder is set) writes `<folder>/Soundbo library.zip` (an old `Rule Forge library.zip` is renamed in place, keeping its Drive id and link). It merges everyone's sound rules (lights dropped, duplicates removed) and clips, and builds byte-identical zips from identical contents (fixed zip timestamps, `created` = newest `updated` among people). A copy is only replaced by a newer `created` (or more sounds), so two admins' apps don't overwrite each other, and it is written in place so Drive keeps its file id. Listeners import it as a pack from its link (`library: true` packs are followed on first import). `src/drive.py` finds a Drive folder from its link: `.shortcut-targets-by-id/<id>/<name>` for shared folders, and the `com.google.drivefs.item-id#S` xattr on macOS for your own (also used for invite links). `POST /api/sharing/join` joins from a folder link or reports `no_drive` / `not_added` (the editor polls it); `GET /api/sharing/invite` returns the folder and library links and whether the library link opens without signing in.

Packaged app: `_enter_app_dir` uses `Application Support/Soundbo` (macOS) or `%APPDATA%\Soundbo` (Windows, unless rules.json sits beside the .exe), first renaming a `dota2-integrations` folder from before the rename. `--tray` (on by default when frozen) runs the asyncio app in a thread and a pystray icon on the main thread (`src/tray.py`); Quit and the power button both end both. On macOS a clicked Dock icon reopens the editor. `dota_setup.install_gsi_config` writes the GSI cfg into every Dota install found through Steam's libraryfolders.vdf, unless a cfg there already targets this port; it is skipped for dev instances with `GSI_PORT` set. `packs.default_library_link()` (`src/library_link.txt`, written by the Build workflow's `library_link` input, or `GSI_LIBRARY`) is fetched and followed on first run.

Uploads never overwrite a different file (`unique_path`) and are decoded with pygame first (`SoundManager.check`), so a broken file is rejected at upload rather than failing mid-game. A second launch finds the port taken (`PortInUse`), and if the running process is this app it opens that editor and exits. Sound files are checked for existence on every `RulesConfig` validation, enabled or not (fail fast): a missing sound makes the editor's save fail, `publish()` refuse to write, and startup exit with the offending rules logged. Deleting a soundboard clip removes it from the sound actions that play it; the first remaining clip takes its odds, and an action with no clips left is removed (logged per rule, `retarget_rules`). The file itself stays in the library, so other rules and friends keep working. In the inspector, every trigger with a rule has a red "Delete" button, which removes only rules. Copying a friend's rule in the editor is all-or-nothing and refused if its sound isn't in your library; followed friends' rules with a missing sound are skipped with a warning. `SoundExecutor` still skips a file that vanishes mid-game.

Requires `lighting_config_{vendor}.json` (e.g. `lighting_config_tapo.json`, auto-created on first run) and an optional `rules.json` in the project root.

## Project Structure

```
src/
├── main.py                    # entry point — wires all subsystems, runs asyncio tasks
├── media.py                   # resolves "media/<file>" to local media/ or the shared folder
├── sharing.py                 # shared-folder settings, publish own rules/clips, read friends, followed rules
├── packs.py                   # sound pack .zip export/import, import from link, update checks, shared library .zip
├── drive.py                   # find a Google Drive folder on disk from its link; Drive ids for invites
├── dota_setup.py              # writes Dota's gamestate_integration cfg
├── tray.py                    # menu bar / tray icon for the packaged app
├── log_setup.py               # stdout + rotating file logging
├── recorder.py                # Recorder — keeps payloads in memory for --record, saves JSONL
├── ingress/
│   └── http_server.py         # POST / handler (logs and strips a top-level `note` field if present), GET /state debug dump, /record/save in record mode
├── state/
│   ├── store.py               # GameState — snapshot store; builds a StateSnapshot per update and runs every monitor
│   ├── items.py               # Items / item type parsing (EmptyItem, NoChargeItem, SingleChargeItem, MultiChargeItem)
│   ├── abilities.py           # Abilities / Ability — one dataclass for every ability slot
│   ├── map.py / hero.py / player.py   # typed parsers
├── rules/
│   ├── config.py              # Pydantic models: Rule, RulesConfig, actions, and the AnyMonitor union (the one list of monitor configs)
│   ├── monitor_config.py      # MonitorType, MonitorConfig base (_create(bus, key), takes_light_priority; build(bus, key) wraps _create and tags the monitor's type)
│   ├── compiler.py            # compile_rules() — one monitor per rule, binds actions to executors; CompiledRules
│   ├── bus.py                 # EventBus — synchronous topic router; Event, EventType
│   ├── monitor_base.py        # StateSnapshot, Monitor ABC, StatefulMonitor (_fire / _end)
│   ├── item_monitors.py       # item / midas / blink configs + monitors + registries
│   ├── ability_monitors.py    # ability config + monitor (cooldown-started tracking)
│   ├── map_monitor.py         # map config + monitor (day/night, pause)
│   ├── hero_monitor.py        # hero config + monitor (killed / respawned)
│   ├── periodic_monitor.py    # periodic and once configs + monitors (game clock)
│   └── actions/
│       ├── base.py            # ActionBinding, ActionExecutor ABC
│       ├── light.py           # LightExecutor — sets/clears LightingArbiter requests
│       ├── sound.py           # SoundExecutor — queue + worker, burst drop
│       └── webhook.py         # WebhookExecutor — queue + worker, cooldown
├── config_ui/
│   ├── routes.py              # /ui editor + /api (config get/put, media list/upload, play, catalog)
│   ├── catalog.py             # hero/ability/item names from dotaconstants, cached in .cache/catalog.json
│   ├── soundboard.py          # soundboard clips API (create/edit/delete/play, link fetch via yt-dlp)
│   ├── files.py               # allowed audio extensions, safe_filename()
│   ├── sharing_routes.py      # /api/sharing (on/off, follow, folder browser) and /api/pack(s) (export, import, refresh, remove)
│   └── static/                # index.html, app.js, app.css (vanilla, no build step)
├── lighting/                  # LightingArbiter, LightingController, vendor drivers (tapo, tuya, log)
└── sound/
    └── manager.py             # SoundManager — async audio playback
tests/                         # pytest
tools/replay.py                # replay / step through recordings
```

## Key Design Decisions

- **No schema assumptions on raw state** — GSI payload is stored as an opaque `dict`; typed state (`Items`, `MapState`) is parsed alongside it.
- **Latest snapshot wins** — each `state.update(data)` fully replaces the previous state.
- **Transport-agnostic state layer** — `GameState` has no aiohttp dependency.
- **Queue handoff** — the HTTP handler only pushes payloads onto an `asyncio.Queue`; the `ingest` task is the single writer that calls `state.update()`.
- **Only timers run before the horn** — updates outside `GAME_IN_PROGRESS` are ignored, except `PRE_GAME` (clock about -1:30 to 0:00), which runs monitors with `runs_before_horn` (`periodic`, `once`). Earlier states (hero selection etc.) have unrelated clock values.
- **No locks** — single writer (the ingest task), multiple readers allowed.
- **Rule engine is compiled at startup** — `compile_rules()` builds one monitor per rule and registers each enabled action on its executor. No runtime routing logic.
- **The bus is a plain topic router** — `EventBus` is synchronous publish/subscribe: a monitor `emit`s (STARTED) or `retract`s (ENDED) an event key, and the executors subscribed to that key handle it, in subscription order. A handler that raises is logged and does not stop the others. The bus knows nothing about actions.
- **Executors own their action type** — `LightExecutor` sets lights on the arbiter synchronously (the arbiter commits once per update); `SoundExecutor` and `WebhookExecutor` put work on their own queue, drained by async workers (`workers()`), so `update()` never does I/O.
- **One monitor per rule, keyed by rule id** — each rule publishes under its own bus key (its id; config validation rejects duplicate ids), so two rules on the same trigger just get separate monitors and every action runs once. The compiler also accepts rules that never went through `RulesConfig` (e.g. followed friends' rules), as long as their ids are unique.
- **Monitors are self-contained** — each monitor module holds its config model (with `_create(bus)`) and its monitor class. All monitors take one `StateSnapshot` (`items`, `prev_items`, `abilities`, `hero`, `player`, `map`) and return early if the part they need is missing.

## State API (`src/state/store.py`)

```python
GameState(compiled_rules, bus, light_arbiter)  # all required, wired once at startup
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
| `periodic`| `PeriodicMonitorConfig` | fires when the game clock passes `k*period + offset` (`period` ≥ 1 s, `offset` -59..59, default 0; optional `min_time` / `max_time` clock seconds, inclusive, limit which triggers fire) |
| `once`   | `OnceMonitorConfig`  | fires once per match when the game clock reaches `time` seconds (may be negative) |

In the editor, periodic and once rules are "Reminders" under Game events; a "Repeats" toggle switches a reminder between the two (off shows just the target game time). Repeating ones have presets (stack camps, bounty, power and wisdom runes, lotus) or a custom timer, with "every", an early/late shift (offset), "from" / "until" (`m:ss`) and a preview of the first play times. Each reminder is its own rule (`reminder_<preset>`); the compiler keys periodic monitors per rule, so two reminders on the same schedule each fire, and `sharing._trigger` keys them by schedule. `periodic` monitors (`periodic_monitor.py`) use `map.clock_time`, which starts negative but never goes backwards. A trigger fires when it lies in (previous clock, current clock]; a gap spanning several triggers fires once, and the first update after start or a match change only records the clock.

`ability` monitors take a `target` — the internal ability name from the GSI `abilities` block (e.g. `spectre_reality`), so no ability list is maintained in code. They only track learned abilities (`level > 0`) and ignore `max_cooldown` (the game reports it unreliably). Choosing an ability that actually has a cooldown is the rule author's responsibility.

### Action types

| `type`         | Fields                  | Notes                                      |
|----------------|-------------------------|--------------------------------------------|
| `play_sound`   | `clips: [{file, probability, volume}]` | Integer probabilities must sum to 100; one clip is picked by weight (a plain sound is one clip at 100) |
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

`uv run python -m src.main --record` keeps every payload in memory; `GET /record/save` writes `recordings/gsi_*.jsonl` (`{"ts", "data"}` per line, optional `"note"`). `tools/replay.py <file>` POSTs a recording to a running app (`--speed`, `--instant`), and `--step` is an interactive stepper (start the app with `--debug` to see fired events) (next N frames, run to next change, diff, state dump, `note` to annotate). Notes live in `<file>.notes.json` keyed by `ts` and are injected into the POSTed JSON as a top-level `note`, which the app logs and strips. `GET /state` returns `{version, raw, events}` after draining the ingest queue (`events` = bus `published` count plus, only when started with `--debug`, the last 100 events; the stepper's `c` stops on new ones and prints them as `FIRED`). Rule ids are not in events; for those check `logs/dota2-integrations.log` for `rule='<id>' ... ->` lines. See the `dota-replay` skill (`.agents/skills/dota-replay/`) for the workflow. When a monitor misbehaves, reproduce it from a recording and inspect the per-frame diff first; the skill has a debugging checklist. Rules with no enabled actions are skipped at compile time, so use a harmless action (e.g. a light) when reproducing a bug.

## Adding a monitor

One new module with the monitor's config model (a `MonitorConfig` subclass: `type`, fields, `_create(bus, key)`, and `takes_light_priority = False` if its lights are the baseline) and its monitor class (`Monitor`, `StatefulMonitor` or `TargetedStatefulMonitor`, `evaluate(snap)` + `clear()`). Then add its `MonitorType` value in `monitor_config.py` and its config class to the `AnyMonitor` union in `config.py`. Nothing else changes: the compiler calls `rule.monitor.build(bus, rule.id)`.

## Build & Release

```bash
uv run pyinstaller --onefile --windowed --paths . --name Soundbo --hidden-import pystray._win32 \
  --add-data "src/config_ui/static:src/config_ui/static" src/main.py   # -> dist/Soundbo.exe
```

The `--add-data` is required: without the editor's static files the server crashes on startup. On startup the app opens the editor (`/ui`) in the default browser; pass `--no-browser` or set `GSI_NO_BROWSER=1` to skip that. The editor's power button (`POST /api/shutdown`) sets the stop event in `main()`, which cancels every task so the port is closed before the process exits.

`.github/workflows/build.yml` (manual) builds Windows (`.exe`) and macOS (`.app` for Apple Silicon and Intel, zipped with `ditto` so the bundle's symlinks and signature survive) from the current code as workflow artifacts. `release.yml` (manual, takes a tag) reuses it and publishes a GitHub release with the binaries plus `rules.example.json` (shipped as `rules.json`: no sounds, lighting disabled, empty actions) and a zip of `.agents/skills`. Both builds are windowed (no console) and keep data in the user's app data folder (see Packaged app above).
