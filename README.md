# dota2-integrations

Receives [Dota 2 GSI](https://developer.valvesoftware.com/wiki/Dota_2_Workshop_Tools/GSI) (Game State Integration) payloads and holds the latest snapshot in memory.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

## Run

```bash
uv run python -m src.main
```

Listens on `http://127.0.0.1:6969`. Configure Dota 2 to POST to this address (see below).

## Record and replay

Capture real game data once, then replay it as often as you like without launching Dota.

```bash
uv run python -m src.main --record      # or the "App (record)" debug target
```

While recording, every incoming payload is kept in memory. Open (or POST to) `http://127.0.0.1:6969/record/save` to write them to `recordings/gsi_<timestamp>.jsonl`, one `{"ts": ..., "data": <payload>}` per line. The endpoint only exists in record mode, and each save contains everything since startup.

Replay is a separate tool, not part of the app. Start the app normally, then:

```bash
uv run python tools/replay.py recordings/<file>.jsonl [--speed 2] [--instant] [--url http://127.0.0.1:6969/]
```

It POSTs the payloads to the running app using the recorded timing (`--speed` scales it, `--instant` removes the delays).

### Step mode and notes

`--step` turns replay into an interactive stepper: send the next N frames, jump to the next change (`c abilities.ability3`), show what changed (`d`), dump the app's raw state (`s [path]`), and see which rules fired. `h` lists the commands.

Frames can be annotated after recording: `note <text>` at the current frame writes `recordings/<file>.notes.json` (keyed by the frame's `ts`). A frame can also carry an inline `"note"` field in its jsonl line. On replay the note is injected into the POSTed JSON as a top-level `note` field; the app logs `GSI note: ...` and strips it before processing.

The stepper reads `GET /state` on the app, which returns the latest raw payload and the rule events fired since the last call.

## Dota 2 Configuration

Create a config file at:

```
<Steam>/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/gamestate_integration_myapp.cfg
```

Minimum contents:

```
"dota2-integrations"
{
    "uri"           "http://127.0.0.1:6969/"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
    }
}
```

## Project Structure

```
src/
├── main.py               # entry point
├── core/runtime.py       # aiohttp server + asyncio event loop
├── ingress/http_handler.py  # POST / handler
└── state/store.py        # GameState — latest-snapshot store
```

## Design

- Incoming payloads are stored as opaque `dict` — no schema assumptions.
- Each new payload fully replaces the previous state (no merging).
- `GameState` has no HTTP dependency; handler receives it via `functools.partial`.
