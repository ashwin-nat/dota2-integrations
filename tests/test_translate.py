import asyncio
import logging
import zipfile

import pytest

from src import translate
from src.rules.bus import Event, EventType
from src.state.events import ChatChannel, ChatMessage


def _event(text):
    return Event("event:chat_message", EventType.STARTED, 1, 1, payload=ChatMessage(1, 3, ChatChannel.TEAM, text))


class FakeDetector:
    def __init__(self, code, confidence=0.9):
        self.result = translate.Detected(code, confidence)

    def detect(self, text):
        return self.result


class FakeModel:
    def translate(self, text):
        return f"EN({text})"


def _translator(detector, models=None):
    t = translate.ChatTranslator()
    t._detector = detector
    t._models = models or {}
    return t


def _handle(t, text):
    asyncio.run(t._handle(_event(text).payload))


def test_detector_skips_short_text_and_finds_russian():
    d = translate.Detector()
    assert d.detect("gg wp") is None
    found = d.detect("ты чего творишь, иди на мид")
    assert found.code == "ru" and found.confidence >= translate.ChatTranslator.MIN_CONFIDENCE
    english = d.detect("what are you doing, go to mid")
    assert english.code == "en"


def test_foreign_message_is_translated_and_logged(caplog):
    t = _translator(FakeDetector("ru"), {"ru": FakeModel()})
    with caplog.at_level(logging.INFO):
        _handle(t, "привет")
    assert "player 3 (ru->en): EN(привет)" in caplog.text


@pytest.mark.parametrize("detector", [FakeDetector("en"), FakeDetector("ru", 0.2), None])
def test_english_unsure_or_undetected_is_left_alone(detector, caplog):
    class NoneDetector:
        def detect(self, text):
            return None

    t = _translator(detector or NoneDetector(), {"ru": FakeModel()})
    with caplog.at_level(logging.INFO):
        _handle(t, "whatever")
    assert "->en" not in caplog.text


def test_missing_model_downloads_once_then_translates_pending(monkeypatch, tmp_path, caplog):
    monkeypatch.chdir(tmp_path)
    downloads = []

    async def fake_download(code):
        downloads.append(code)
        await asyncio.sleep(0)

    monkeypatch.setattr(translate, "download_model", fake_download)
    monkeypatch.setattr(translate, "Model", lambda directory: FakeModel())
    monkeypatch.setattr(translate, "model_installed", lambda code: bool(downloads))

    async def scenario():
        t = _translator(FakeDetector("ru"))
        await t._handle(_event("один").payload)
        await t._handle(_event("два").payload)
        await asyncio.gather(*t._downloading.values())
        return t

    with caplog.at_level(logging.INFO):
        asyncio.run(scenario())
    assert downloads == ["ru"]
    assert "EN(один)" in caplog.text and "EN(два)" in caplog.text


def test_failed_download_is_not_retried_straight_away(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = []

    async def failing(code):
        calls.append(code)
        raise OSError("offline")

    monkeypatch.setattr(translate, "download_model", failing)

    async def scenario():
        t = _translator(FakeDetector("ru"))
        await t._handle(_event("один").payload)
        await asyncio.gather(*t._downloading.values(), return_exceptions=True)
        await t._handle(_event("два").payload)
        assert not t._downloading

    asyncio.run(scenario())
    assert calls == ["ru"]


def test_full_queue_drops_instead_of_blocking(caplog):
    async def scenario():
        t = translate.ChatTranslator()
        for _ in range(translate.ChatTranslator.QUEUE_SIZE + 1):
            t.on_chat(_event("привет"))

    with caplog.at_level(logging.WARNING):
        asyncio.run(scenario())
    assert "dropping" in caplog.text


def test_extract_package_keeps_only_model_and_tokenizer(tmp_path):
    archive = tmp_path / "p.argosmodel"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("translate-ru_en-1_9/sentencepiece.model", "sp")
        z.writestr("translate-ru_en-1_9/model/model.bin", "bin")
        z.writestr("translate-ru_en-1_9/model/config.json", "{}")
        z.writestr("translate-ru_en-1_9/stanza/ru/tokenize/x.pt", "big")
        z.writestr("translate-ru_en-1_9/README.md", "hi")
    dest = tmp_path / "ru_en"
    translate.extract_package(archive, dest)
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == [
        "model/config.json", "model/model.bin", "sentencepiece.model",
    ]
    assert not (tmp_path / "ru_en.partial").exists()


def test_extract_package_rejects_non_translation_zip(tmp_path):
    archive = tmp_path / "bad.argosmodel"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("x/readme", "nope")
    with pytest.raises(ValueError):
        translate.extract_package(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists() and not (tmp_path / "out.partial").exists()


def test_chat_is_logged_even_without_a_worker(caplog):
    t = translate.ChatTranslator()
    with caplog.at_level(logging.INFO):
        t.on_chat(_event("hello"))
    assert "Chat [team] player 3: hello" in caplog.text


def test_chat_logging_survives_bus_reset(caplog):
    from src.rules.bus import EventBus
    from src.state.events import EventProcessor, event_key

    bus = EventBus()
    bus.subscribe(event_key("chat_message"), translate.ChatTranslator().on_chat, persistent=True)
    bus.reset()
    with caplog.at_level(logging.INFO):
        EventProcessor(bus).process([{"game_time": 1, "event_type": "chat_message", "player_id": 3,
                                      "channel_type": 12, "message": "hello"}])
    assert "Chat [team] player 3: hello" in caplog.text


def test_clean_leftovers_removes_only_unfinished_downloads(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    models = tmp_path / "translate_models"
    (models / "ru_en" / "model").mkdir(parents=True)
    (models / "es_en.partial" / "model").mkdir(parents=True)
    (models / "tmpabc.argosmodel").write_bytes(b"half")
    translate.clean_leftovers()
    assert sorted(p.name for p in models.iterdir()) == ["ru_en"]


def test_clean_leftovers_without_a_models_folder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    translate.clean_leftovers()
