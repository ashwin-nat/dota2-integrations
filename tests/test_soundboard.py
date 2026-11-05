import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from src import sharing
from src.config_ui import soundboard
from src.config_ui.soundboard import setup_soundboard


def _clip(file, probability):
    return {"file": file, "probability": probability, "volume": 50}


@pytest.mark.asyncio
async def test_deleting_a_clip_changes_the_rules_but_keeps_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(soundboard, "SOUNDBOARD_PATH", tmp_path / "soundboard.json")
    monkeypatch.setattr(sharing, "publish_safely", lambda: None)
    media = tmp_path / "media"
    media.mkdir()
    (media / "a.mp3").write_bytes(b"a")
    (media / "b.mp3").write_bytes(b"b")
    (tmp_path / "soundboard.json").write_text(json.dumps({"clips": [
        {"id": "x", "name": "a", "file": "media/a.mp3", "duration": 1.0},
    ]}))
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps({"rules": [
        {"id": "two", "monitor": {"type": "hero", "event": "HERO_KILLED"}, "actions": [
            {"type": "play_sound", "clips": [_clip("media/a.mp3", 70), _clip("media/b.mp3", 30)]},
        ]},
    ]}))
    reloaded = []
    app = web.Application()
    setup_soundboard(app, None, rules_path, reloaded.append)

    async with TestClient(TestServer(app)) as client:
        response = await client.delete("/api/soundboard/x")
        assert response.status == 200

    assert (media / "a.mp3").is_file()
    assert json.loads((tmp_path / "soundboard.json").read_text())["clips"] == []
    clips = json.loads(rules_path.read_text())["rules"][0]["actions"][0]["clips"]
    assert [(c["file"], c["probability"]) for c in clips] == [("media/b.mp3", 100)]
    assert len(reloaded) == 1
