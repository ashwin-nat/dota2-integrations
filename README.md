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

The ⏻ button at the top right turns the app off: it stops the server and frees the port, which is handy for the macOS app because it has no window to quit from.

The **Soundboard** tab works like Discord's soundboard. Add a clip from an audio file, a video file (.mp4, .webm, .mov) or a link (YouTube, Twitch clips, TikTok, X and other sites yt-dlp supports). Trim it to at most 5.2 seconds on the waveform, then give it a name, an emoji and a volume. Clicking a tile plays the clip on this PC's speakers. Each clip is saved as an MP3 named after it (`media/<name>.mp3`), so you can also pick it as the sound for items, abilities and game events. Renaming a clip renames the file and updates the rules that use it. Deleting a clip switches those rule sounds off. Clip details (emoji, volume) are kept in `soundboard.json`.

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
