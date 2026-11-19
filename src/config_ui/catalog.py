from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from pathlib import Path
from typing import Any

import aiohttp
import certifi

logger = logging.getLogger(__name__)

# Community-maintained dump of the game's hero / ability / item data (same
# source OpenDota uses). The newest release is used; PINNED_VERSION is the fallback
# so a bad upstream release can't break the UI.
DOTACONSTANTS_URL = "https://cdn.jsdelivr.net/npm/dotaconstants@{version}/build/{name}.json"
# jsDelivr's package index; `tags.latest` is the newest published release, which tracks the newest game patch
LATEST_VERSION_URL = "https://data.jsdelivr.com/v1/package/npm/dotaconstants"
# Used when the latest version can't be looked up, or its data fails to build into a catalog
PINNED_VERSION = "10.9.0"
CACHE_PATH = Path(".cache/catalog.json")
CATALOG_VERSION = 3  # bump when _build's output shape changes so stale caches refresh
CHECK_INTERVAL = 6 * 3600  # seconds between looking for a newer game version
_fetch_lock = asyncio.Lock()
_last_check: float | None = None  # time.monotonic() of the last version lookup; None until the first one

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


async def _fetch(session: aiohttp.ClientSession, version: str, name: str) -> Any:
    async with session.get(DOTACONSTANTS_URL.format(version=version, name=name), timeout=aiohttp.ClientTimeout(total=30)) as resp:
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


def _build(heroes: dict, hero_abilities: dict, abilities: dict, items: dict, game_version: str = PINNED_VERSION) -> dict:
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
            hero_abs.append({"key": ab_key, "name": ab["dname"], "desc": ab.get("desc") or "", "has_cd": _has_cooldown(ab.get("cd"))})
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

    return {"v": CATALOG_VERSION, "game_version": game_version, "heroes": hero_list, "items": item_list}


def _read_cache() -> dict | None:
    try:
        return json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return None  # missing or corrupt: treat as no cache


def _session() -> aiohttp.ClientSession:
    # Python.org builds on macOS ship without system CA certs
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where())))


async def _latest_version() -> str | None:
    """Newest dotaconstants release, or None when the lookup fails (offline, CDN down)."""
    try:
        async with _session() as session:
            async with session.get(LATEST_VERSION_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                resp.raise_for_status()
                return (await resp.json(content_type=None))["tags"]["latest"]
    except Exception as e:
        logger.warning(f"Could not look up the latest Dota data version: {e}")
        return None


async def load_catalog() -> dict | None:
    """Return the catalog for the newest game version, refreshing the cache when the game version changed.

    The version is looked up at most every CHECK_INTERVAL. If the lookup, the download or the build of
    the new data fails, the cached catalog keeps being served. None when offline with no cache.
    """
    global _last_check
    async with _fetch_lock:
        cached = _read_cache()
        if cached and cached.get("v") != CATALOG_VERSION:
            cached = None  # older output shape (e.g. before ability descriptions): needs a rebuild
        now = time.monotonic()
        if cached and cached.get("game_version") and _last_check is not None and now - _last_check < CHECK_INTERVAL:
            return cached
        _last_check = now
        latest = await _latest_version()
        if cached and (latest is None or latest == cached.get("game_version")):
            return cached
        if latest:
            logger.info(f"Dota data {cached['game_version'] if cached else 'none'} -> {latest}, refreshing the catalog")
            fresh = await _download(latest)
            if fresh:
                return fresh
        if cached:
            return cached
        # Nothing cached and the newest version didn't work: the pinned one is known to build
        return await _download(PINNED_VERSION) if latest != PINNED_VERSION else None


async def _download(version: str) -> dict | None:
    try:
        async with _session() as session:
            raw = [await _fetch(session, version, n) for n in ("heroes", "hero_abilities", "abilities", "items")]
        catalog = _build(*raw, game_version=version)
    except Exception as e:
        logger.warning(f"Could not build the Dota catalog from dotaconstants {version}: {e}")
        return None
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(catalog))
    logger.info(f"Dota catalog ({version}) cached at {CACHE_PATH}")
    return catalog
