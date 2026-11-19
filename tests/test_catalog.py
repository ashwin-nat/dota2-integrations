import json
from pathlib import Path

import pytest

from src.config_ui import catalog


def _write_cache(version: str, v: int = catalog.CATALOG_VERSION) -> dict:
    data = {"v": v, "game_version": version, "heroes": [], "items": [{"key": "item_old"}]}
    Path(".cache").mkdir(exist_ok=True)
    Path(".cache/catalog.json").write_text(json.dumps(data))
    return data


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh cache folder, no throttle, and stubs for the network: .latest is the lookup result,
    .downloads records the versions downloaded, .broken lists versions whose download fails."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(catalog, "_last_check", None)

    class Env:
        latest: str | None = "10.9.0"
        downloads: list[str] = []
        broken: set[str] = set()

    e = Env()
    e.downloads = []
    e.broken = set()

    async def fake_latest():
        return e.latest

    async def fake_download(version):
        e.downloads.append(version)
        if version in e.broken:
            return None
        data = {"v": catalog.CATALOG_VERSION, "game_version": version, "heroes": [], "items": [{"key": f"item_{version}"}]}
        Path(".cache").mkdir(exist_ok=True)
        Path(".cache/catalog.json").write_text(json.dumps(data))
        return data

    monkeypatch.setattr(catalog, "_latest_version", fake_latest)
    monkeypatch.setattr(catalog, "_download", fake_download)
    return e


@pytest.mark.asyncio
async def test_new_game_version_replaces_the_cache(env):
    _write_cache("10.8.0")
    got = await catalog.load_catalog()
    assert got["game_version"] == "10.9.0"
    assert env.downloads == ["10.9.0"]


@pytest.mark.asyncio
async def test_same_version_is_not_downloaded_again(env):
    _write_cache("10.9.0")
    got = await catalog.load_catalog()
    assert got["items"] == [{"key": "item_old"}]
    assert env.downloads == []


@pytest.mark.asyncio
async def test_version_is_only_looked_up_every_check_interval(env, monkeypatch):
    _write_cache("10.8.0")
    await catalog.load_catalog()
    env.latest = "11.0.0"
    got = await catalog.load_catalog()
    assert got["game_version"] == "10.9.0"  # not asked again yet
    monkeypatch.setattr(catalog, "_last_check", catalog._last_check - catalog.CHECK_INTERVAL - 1)
    got = await catalog.load_catalog()
    assert got["game_version"] == "11.0.0"


@pytest.mark.asyncio
async def test_offline_keeps_serving_the_cache(env):
    _write_cache("10.8.0")
    env.latest = None
    got = await catalog.load_catalog()
    assert got["game_version"] == "10.8.0"
    assert env.downloads == []


@pytest.mark.asyncio
async def test_failed_new_version_keeps_the_cache(env):
    _write_cache("10.8.0")
    env.broken.add("10.9.0")
    got = await catalog.load_catalog()
    assert got["game_version"] == "10.8.0"


@pytest.mark.asyncio
async def test_no_cache_and_broken_latest_falls_back_to_the_pinned_version(env):
    env.latest = "99.0.0"
    env.broken.add("99.0.0")
    got = await catalog.load_catalog()
    assert got["game_version"] == catalog.PINNED_VERSION
    assert env.downloads == ["99.0.0", catalog.PINNED_VERSION]


@pytest.mark.asyncio
async def test_no_cache_and_offline_uses_the_pinned_version(env):
    env.latest = None
    got = await catalog.load_catalog()
    assert got is not None and got["game_version"] == catalog.PINNED_VERSION


@pytest.mark.asyncio
async def test_cache_from_an_older_shape_is_rebuilt(env):
    _write_cache("10.9.0", v=catalog.CATALOG_VERSION - 1)
    got = await catalog.load_catalog()
    assert got["v"] == catalog.CATALOG_VERSION
    assert env.downloads == ["10.9.0"]
