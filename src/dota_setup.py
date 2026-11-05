"""Point Dota 2 at this app by writing its Game State Integration config, so nobody has to.

Dota reads every cfg/gamestate_integration/gamestate_integration_*.cfg at launch and POSTs
game state to each one's "uri". Steam can keep games in several library folders, listed
in steamapps/libraryfolders.vdf.
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CFG_NAME = "gamestate_integration_soundbo.cfg"
DOTA_CFG = Path("steamapps", "common", "dota 2 beta", "game", "dota", "cfg")

CFG_TEMPLATE = """"soundbo"
{{
    "uri"           "http://127.0.0.1:{port}/"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {{
        "buildings"     "1"
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
        "draft"         "1"
        "wearables"     "1"
        "events"        "1"
    }}
}}
"""


def _steam_roots() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Steam"]
    if sys.platform == "win32":
        roots = []
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
        return roots + [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    return [home / ".steam" / "steam", home / ".local" / "share" / "Steam"]


def _libraries(root: Path) -> list[Path]:
    libs = [root]
    try:
        vdf = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libs += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    except OSError:
        pass
    return libs


def dota_cfg_dirs() -> list[Path]:
    seen: set[Path] = set()
    out = []
    for root in _steam_roots():
        for lib in _libraries(root):
            cfg = lib / DOTA_CFG
            key = cfg.resolve() if cfg.exists() else cfg
            if key not in seen and cfg.is_dir():
                seen.add(key)
                out.append(cfg)
    return out


def install_gsi_config(port: int) -> list[Path]:
    """Write the config into every Dota install that doesn't send to this port yet."""
    written = []
    for cfg in dota_cfg_dirs():
        folder = cfg / "gamestate_integration"
        try:
            folder.mkdir(exist_ok=True)
            ours = re.compile(rf"(127\.0\.0\.1|localhost):{port}\b")
            if any(ours.search(f.read_text(encoding="utf-8", errors="replace")) for f in folder.glob("gamestate_integration_*.cfg")):
                continue
            (folder / CFG_NAME).write_text(CFG_TEMPLATE.format(port=port), encoding="utf-8")
            written.append(folder / CFG_NAME)
            logger.info(f"Set up Dota 2 to send game state here: {folder / CFG_NAME} (restart Dota if it's running)")
        except OSError as e:
            logger.warning(f"Could not write the Dota 2 config in {folder}: {e}")
    return written
