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

### Sharing with friends

The **Friends & packs** tab shares sounds, soundboard clips and rules. Everyone keeps their own rules. For each friend or pack you can:

- **Copy** a rule into yours. If you already have a sound for that trigger, you choose **Replace mine** (only the sound changes; your lights stay) or **Add both**.
- Turn on **Play their sounds too**. Their sounds then fill in triggers you don't have a sound for. Your own sound always wins, so two sounds never play at once.

Lights, webhooks (they can hold API keys), logs and light passwords always stay on your computer. There are two ways to share.

**Sound packs (no install).** **Export my pack** downloads one `.zip` with your rules, soundboard clips and the sounds they use.
- **Sharing yours:** upload the `.zip` to Google Drive in your browser and set its access to *Anyone with the link*. Then send the link.
- **Adding a friend's:** paste their link into the Friends tab, or drop their `.zip` on it.
- **Updates:** packs added from a link are checked for updates every 30 minutes. To publish an update, open the file in Drive and use **Manage versions** to upload the new `.zip`, so the link stays the same. Dropbox links and plain https links work too.
- **Name clashes:** a pack's sound whose name clashes with a different sound you already have is stored under a new name, such as `wow (2).mp3`.

**Shared folder (automatic, both ways).** For friends who run a sync app:

1. Everyone installs [Google Drive for desktop](https://www.google.com/drive/download/).
2. One person creates a folder (for example *Dota Sounds*) and shares it with the others as **Editor**.
3. Everyone else opens it under *Shared with me*, right-clicks it, and picks **Organize → Add shortcut** to put it in My Drive, so it syncs to their computer.
4. Make the folder **Available offline** (right-click it) or set Drive to **Mirror files**, so a sound doesn't have to download the first time it plays mid-game.
5. In the editor, open **Friends**, enter your name and pick the folder. Google Drive, Dropbox, OneDrive and iCloud folders are listed automatically.

When you join, your sounds are copied into `<folder>/media/`, and from then on everyone's sounds play from there. If a friend already put a *different* sound there with the same name, yours is copied as `name (2).mp3` and your rules are updated to use it. Your rules and clip names are written to `<folder>/people/<your name>.json` every time you save. Nobody else writes that file, so the sync never produces conflicting copies. If you stop sharing, the shared sounds are copied back to your computer, so your rules keep working.

The **Soundboard** tab works like Discord's soundboard. Add a clip from an audio file, a video file (.mp4, .webm, .mov) or a link (YouTube, Twitch clips, TikTok, X and other sites yt-dlp supports). Trim it to at most 5.2 seconds on the waveform, then give it a name, an emoji and a volume. Clicking a tile plays the clip on this PC's speakers. Each clip is saved as an MP3 named after it (`media/<name>.mp3`), so you can also pick it as the sound for items, abilities and game events. Renaming a clip renames the file and updates the rules that use it. Deleting a clip switches those rule sounds off. Clip details (emoji, volume) are kept in `soundboard.json`.

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
