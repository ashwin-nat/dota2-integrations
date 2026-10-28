---
name: dota-setup
description: First-time setup of the dota2-integrations app on a machine — install deps, install the Dota 2 GSI config into the game folder, choose and configure a lighting vendor (Tapo, Tuya, log, or none), and smoke-test the receiver. Use when the user asks to set up, install, or get the app running, or when Dota isn't sending data / the lights aren't connecting. Not for adding or editing rules (use dota-rules).
---

# dota2-integrations setup

Walk the user through setup one step at a time. Check what is already done before doing it; skip finished steps instead of redoing them. Ask before overwriting any existing file.

## 1. Python deps

- Check `uv` is on PATH (`Get-Command uv`). If it isn't, point the user to https://docs.astral.sh/uv/ and stop. Don't install it yourself.
- Run `uv sync`. It installs Python 3.13 and the deps from `pyproject.toml` (aiohttp, pydantic, pygame, python-kasa, tinytuya).

## 2. Dota 2 GSI config

Dota POSTs game state to the app only if a config file sits in its `gamestate_integration` folder.

**Find the install** (Windows):
1. Steam root: `(Get-ItemProperty 'HKCU:\Software\Valve\Steam').SteamPath`
2. Read `<SteamPath>\steamapps\libraryfolders.vdf` and find the library whose `apps` block has `"570"` (Dota 2). It is often not the Steam root.
3. Target folder: `<library>\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration\`. Create it if missing.

On Linux the default Steam root is `~/.steam/steam`, on macOS `~/Library/Application Support/Steam`; the rest of the path is the same.

**List the folder first.** If a cfg already points at `http://127.0.0.1:6969/`, setup is already done; show it to the user and move on.

Otherwise write `gamestate_integration_dota2integrations.cfg`:

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

The port is hard-coded in `src/ingress/http_server.py`. If the user changes it there, change the `uri` here too.

Tell the user to:
- restart Dota, which only reads GSI configs at launch

## 3. Lighting

Settings live in two places:
- `rules.json` → `"lighting": { "enabled": bool, "vendor": "tapo" | "tuya" | "log" }`. If `rules.json` is missing, it is created with defaults on first run (`enabled: false`).
- `lighting_config_{vendor}.json` → device connection details. The fields come from each driver's `get_empty_config()` in `src/lighting/drivers/`; read that file to get the current field list.

Ask which setup the user has:

| Choice | `rules.json` lighting | Device config |
|---|---|---|
| No lights | `enabled: false` | none |
| Test without hardware | `enabled: true, vendor: "log"` | none; colour changes are only logged |
| TP-Link Tapo / Kasa bulb | `enabled: true, vendor: "tapo"` | `lighting_config_tapo.json`: `ipaddr`, `username`, `password` (the Tapo app account login) |
| Tuya / Smart Life bulb | `enabled: true, vendor: "tuya"` | `lighting_config_tuya.json`: `device_id`, `ip_address`, `local_key`, `version` (default 3.3) |

Finding device details:
- Tapo: `uv run kasa discover` lists IPs on the LAN.
- Tuya: `uv run python -m tinytuya scan` finds the IP, device ID and protocol version. The `local_key` needs a Tuya IoT developer account and `uv run python -m tinytuya wizard`. This is interactive, so the user has to run it themselves.

Write the device config yourself, with the secret fields (`password`, `local_key`) left blank. Then ask the user to fill those in themselves, so the secrets never pass through the chat. All `*.json` files are gitignored, so the file won't be committed.

If lighting is enabled and the vendor config file is missing when the app starts, the app writes a blank template and keeps running with lights off (logged as a warning). Fill it in and restart.

## 4. Sounds

Sound files go in `media/`, which is gitignored, so each machine needs its own copy. Rules reference them by path relative to the project root (e.g. `media/wow.mp3`). Global volume is `rules.json` → `"sound": { "volume": 0-100 }`. If `media/` is empty, mention it; rules that point at missing files fail validation on startup.

## 5. Smoke test

1. Start the app in the background: `uv run python -m src.main`.
2. In the output (also written to `logs/dota2-integrations.log`), look for `Rule engine ready: …` and `Listening on http://127.0.0.1:6969`. For tapo/tuya, a connection error at startup means the IP or credentials are wrong.
3. Check the endpoint: POST `{}` to `http://127.0.0.1:6969/`. It should return `OK`. Payloads from outside a running match are ignored by design.
4. Ask the user to launch Dota and start a demo hero or a bot match. The log should print `Hero abilities:` once the match is in progress. That confirms GSI data is arriving.
5. Stop the background app when done.

If nothing arrives: check the cfg is in the right library folder, the launch option is set, Dota was restarted, and nothing else is using port 6969.

## 6. Hand off

Once the smoke test passes, ask if the user wants to set up some rules now. If yes, continue with the `dota-rules` skill.
