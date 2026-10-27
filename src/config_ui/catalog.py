from __future__ import annotations

import asyncio
import json
import logging
import ssl
from pathlib import Path
from typing import Any

import aiohttp
import certifi

logger = logging.getLogger(__name__)

# Community-maintained dump of the game's hero / ability / item data (same
# source OpenDota uses). Pinned so a bad upstream release can't break the UI.
DOTACONSTANTS_URL = "https://cdn.jsdelivr.net/npm/dotaconstants@10.8.0/build/{name}.json"
CACHE_PATH = Path(".cache/catalog.json")
_fetch_lock = asyncio.Lock()

_ITEM_GROUPS = {
    "consumable": "Consumables",
    "consumable;laning": "Consumables",
    "component": "Basics",
    "secret_shop": "Secret Shop",
    "common": "Upgrades",
    "rare": "Upgrades",
    "epic": "Upgrades",
    "artifact": "Upgrades",
}


async def _fetch(session: aiohttp.ClientSession, name: str) -> Any:
    async with session.get(DOTACONSTANTS_URL.format(name=name), timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


def _has_cooldown(cd: Any) -> bool:
    if isinstance(cd, list):
        return any(_has_cooldown(c) for c in cd)
    try:
        return float(cd) > 0
    except (TypeError, ValueError):
        return False


def _flatten(keys: list) -> list[str]:
    # Some heroes list alternate ability sets as nested lists
    out: list[str] = []
    for k in keys:
        out.extend(_flatten(k) if isinstance(k, list) else [k])
    return out


def _build(heroes: dict, hero_abilities: dict, abilities: dict, items: dict) -> dict:
    """Trim the raw dumps down to what the editor needs: keys, display names, cooldown flags."""
    hero_list = []
    for hero in heroes.values():
        npc = hero["name"]
        key = npc.removeprefix("npc_dota_hero_")
        hero_abs = []
        for ab_key in dict.fromkeys(_flatten(hero_abilities.get(npc, {}).get("abilities", []))):
            ab = abilities.get(ab_key) or {}
            if not ab.get("dname") or ab_key.endswith("_stop") or "generic_hidden" in ab_key:
                continue
            hero_abs.append({"key": ab_key, "name": ab["dname"], "has_cd": _has_cooldown(ab.get("cd"))})
        hero_list.append({
            "key": key,
            "name": hero.get("localized_name", key),
            "attr": hero.get("primary_attr"),
            "abilities": hero_abs,
        })
    hero_list.sort(key=lambda h: h["name"])

    item_list = []
    for key, item in items.items():
        if key.startswith("recipe_") or not item.get("dname"):
            continue
        group = "Neutral" if item.get("tier") else _ITEM_GROUPS.get(item.get("qual") or "")
        if group is None:
            continue
        item_list.append({
            "key": f"item_{key}",
            "img": key,
            "name": item["dname"],
            "cost": item.get("cost") or 0,
            "group": group,
            # Charge-based items like Midas report cd=False but still have an active
            "has_cd": _has_cooldown(item.get("cd")) or any(ab.get("type") == "active" for ab in item.get("abilities") or []),
        })
    item_list.sort(key=lambda i: (i["cost"], i["name"]))

    return {"heroes": hero_list, "items": item_list}


async def load_catalog() -> dict | None:
    """Return the cached catalog, fetching it once if missing. None when offline with no cache."""
    async with _fetch_lock:
        if CACHE_PATH.exists():
            return json.loads(CACHE_PATH.read_text())
        return await _download()


async def _download() -> dict | None:
    try:
        # Python.org builds on macOS ship without system CA certs
        connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))
        async with aiohttp.ClientSession(connector=connector) as session:
            raw = [await _fetch(session, n) for n in ("heroes", "hero_abilities", "abilities", "items")]
    except Exception as e:
        logger.warning(f"Could not fetch Dota catalog: {e}")
        return None
    catalog = _build(*raw)
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(catalog))
    logger.info(f"Dota catalog cached at {CACHE_PATH}")
    return catalog
