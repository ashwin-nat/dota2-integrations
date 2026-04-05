# CLAUDE.md

## Project

Dota 2 GSI (Game State Integration) receiver. Accepts raw POST payloads from the Dota 2 client, holds the latest snapshot in memory, and drives a rule engine that triggers sound/lighting actions on game events.

## Tech Stack

- Python 3.13
- `asyncio` — async runtime
- `aiohttp` — HTTP server
- `pydantic` — rule/action config validation
- `uv` — dependency and environment management

## Running

```bash
uv run python -m src.main
```

Listens on `http://127.0.0.1:6969`. Dota 2 sends POST requests to `/`.

Requires `lighting_config.json` (auto-created on first run) and an optional `rules.json` in the project root.

## Project Structure

```
src/
├── main.py                    # entry point — wires all subsystems, runs asyncio tasks
├── ingress/
│   └── http_server.py         # POST / handler; emits EventCode.INCOMING_DATA on each payload
├── state/
│   ├── store.py               # GameState — snapshot store, drives rule monitors on every update
│   ├── items.py               # Items / item type parsing (EmptyItem, NoChargeItem, SingleChargeItem, MultiChargeItem)
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
│   └── map_monitor.py         # MapMonitor — day/night cycle transition detector
├── monitors/
│   ├── base.py                # Monitor ABC
│   └── day_night.py           # Legacy day/night monitor (pre-rule-engine)
├── lighting/
│   └── controller.py          # LightingController — Philips Hue RGB control
└── sound/
    └── manager.py             # SoundManager — async audio playback
```

## Key Design Decisions

- **No schema assumptions on raw state** — GSI payload is stored as an opaque `dict`; typed state (`Items`, `MapState`) is parsed alongside it.
- **Latest snapshot wins** — each `state.set(data)` fully replaces the previous state.
- **Transport-agnostic state layer** — `GameState` has no aiohttp dependency.
- **Type-safe handler injection** — HTTP handler receives `EventBus` as a bound arg, emits `INCOMING_DATA`; `GameState` subscribes to that event.
- **No locks** — single writer (HTTP handler via event bus), multiple readers allowed.
- **Rule engine is compiled at startup** — `compile_rules()` parses `rules.json` once into `CompiledRules` (lists of monitor instances pre-wired to `RuleEventBus`). No runtime routing logic.
- **Two async buses** — `EventBus` for internal infrastructure events; `RuleEventBus` for string-key rule events dispatched to `ActionExecutor`.

## State API (`src/state/store.py`)

```python
state.get()                      # -> dict | None       current raw snapshot
state.set(data)                  # -> None              replace snapshot, run rule monitors
state.version()                  # -> int               monotonic counter, increments on every set
state.set_compiled_rules(rules)  # -> None              attach CompiledRules once at startup
state.items                      # -> Items | None       parsed item slots
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

### Action types

| `type`         | Fields                  | Notes                                      |
|----------------|-------------------------|--------------------------------------------|
| `play_sound`   | `file: str`             |                                            |
| `light`        | `r`, `g`, `b` (0–255)  |                                            |
| `reset_light`  | _(none)_                | Restores day/night colour from `map_colours`; forbidden on map monitors |
| `logger`       | `message: str`          |                                            |

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
