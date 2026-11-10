import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from pydantic import ValidationError

from src import media, sharing
from src.config_ui import soundboard
from src.config_ui.soundboard import setup_soundboard
from src.rules.config import RulesConfig


def _rules(*files):
    return {"rules": [
        {"id": f"r{i}", "monitor": {"type": "hero", "event": "HERO_KILLED"},
         "actions": [{"type": "play_sound", "clips": [{"file": f, "probability": 100}]}]}
        for i, f in enumerate(files)
    ]}


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fresh app folder with sharing off; module state is restored afterwards."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(media, "_media_dir", media.LOCAL_MEDIA_DIR)
    monkeypatch.setattr(sharing, "_settings", sharing.SharingSettings(name="Me"))
    Path("media").mkdir()
    return tmp_path


def _shared(home, name="Drive"):
    folder = home / name / "Dota Sounds"
    (folder / "media").mkdir(parents=True)
    (folder / "people").mkdir()
    return folder


def test_missing_sound_fails_validation_but_loads_for_the_running_app(home):
    Path("rules.json").write_text(json.dumps(_rules("media/gone.mp3")))
    with pytest.raises(ValidationError):
        RulesConfig.load(Path("rules.json"))
    config = RulesConfig.load(Path("rules.json"), allow_missing_sounds=True)
    assert config.missing_sounds() == [("r0", "media/gone.mp3")]


def test_starts_when_drive_is_not_mounted_and_switches_when_it_is(home):
    folder = _shared(home)
    (folder / "media" / "horn.mp3").write_bytes(b"x")
    Path("rules.json").write_text(json.dumps(_rules("media/horn.mp3")))
    Path("sharing.json").write_text(json.dumps({"folder": str(folder), "name": "Me"}))
    offline = home / "Drive-offline"
    (home / "Drive").rename(offline)

    sharing.load()
    config = RulesConfig.load(Path("rules.json"), allow_missing_sounds=True)
    assert config.missing_sounds() == [("r0", "media/horn.mp3")]
    assert sharing.reconnect() is False

    offline.rename(home / "Drive")
    assert sharing.reconnect() is True
    assert RulesConfig.load(Path("rules.json")).missing_sounds() == []
    assert sharing.reconnect() is False


def test_changing_shared_folder_brings_the_sounds_along(home):
    old, new = _shared(home, "A"), _shared(home, "B")
    (old / "media" / "horn.mp3").write_bytes(b"x")
    Path("rules.json").write_text(json.dumps(_rules("media/horn.mp3")))
    Path("sharing.json").write_text(json.dumps({"folder": str(old), "name": "Me"}))
    sharing.load()

    sharing.configure(str(new), "Me")

    assert (new / "media" / "horn.mp3").read_bytes() == b"x"
    assert RulesConfig.load(Path("rules.json")).missing_sounds() == []
    assert (new / "people" / "Me.json").exists()


def test_a_rule_with_a_missing_sound_does_not_stop_sharing_from_turning_on(home):
    folder = _shared(home)
    Path("rules.json").write_text(json.dumps(_rules("media/gone.mp3")))
    sharing.load()

    sharing.configure(str(folder), "Me")

    assert sharing.shared_folder() == folder
    assert not (folder / "people" / "Me.json").exists()  # publish still refuses a broken rule


@pytest.mark.asyncio
async def test_renaming_a_shared_clip_keeps_the_old_file_for_friends(home, monkeypatch):
    folder = _shared(home)
    (folder / "media" / "horn.mp3").write_bytes(b"x")
    monkeypatch.setattr(sharing, "_settings", sharing.SharingSettings(name="Me", folder=str(folder)))
    monkeypatch.setattr(sharing, "publish_safely", lambda: None)
    media.set_media_dir(folder / "media")
    monkeypatch.setattr(soundboard, "SOUNDBOARD_PATH", home / "soundboard.json")
    (home / "soundboard.json").write_text(json.dumps({"clips": [
        {"id": "x", "name": "horn", "file": "media/horn.mp3", "duration": 1.0},
    ]}))
    rules_path = home / "rules.json"
    rules_path.write_text(json.dumps(_rules("media/horn.mp3")))
    app = web.Application()
    setup_soundboard(app, None, rules_path, lambda config: None)

    async with TestClient(TestServer(app)) as client:
        response = await client.patch("/api/soundboard/x", json={"name": "big horn"})
        assert response.status == 200

    assert (folder / "media" / "horn.mp3").is_file()
    assert (folder / "media" / "big horn.mp3").is_file()
    clip = json.loads(rules_path.read_text())["rules"][0]["actions"][0]["clips"][0]
    assert clip["file"] == "media/big horn.mp3"
