# dota2-integrations

Receives [Dota 2 GSI](https://developer.valvesoftware.com/wiki/Dota_2_Workshop_Tools/GSI) (Game State Integration) payloads and holds the latest snapshot in memory.

## Download (no Python needed)

Grab the latest build from the [Releases page](https://github.com/ashwin-nat/dota2-integrations/releases):

- **Windows:** `dota2-integrations-windows.exe`. Put it in its own folder; `rules.json`, sounds and logs live next to it.
- **Mac (Apple Silicon, M1 and later):** `dota2-integrations-mac.zip`
- **Mac (Intel):** `dota2-integrations-mac-intel.zip`

Starting the app opens the rules editor in your browser.

**First launch on Mac:** the app isn't signed by Apple, so macOS blocks it the first time. Unzip it, move it to Applications, double-click it, then go to **System Settings → Privacy & Security** and click **Open Anyway**. If macOS says the app "is damaged", run this once in Terminal:

```bash
xattr -dr com.apple.quarantine /Applications/dota2-integrations.app
```

The Mac app keeps its settings, sounds and logs in `~/Library/Application Support/dota2-integrations/`.

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

Open `http://127.0.0.1:6969/ui` to edit rules in the browser: pick items from a shop-style grid or abilities from a hero's page, attach sounds (with preview and drag-and-drop upload), light colours or webhooks, and save. Changes apply immediately without a restart.

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
