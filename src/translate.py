"""Live translation of non-English chat into English, fully offline and free.

Language detection is `lingua`; translation is CTranslate2 running the Argos Translate (Opus-MT) models.
The Argos *library* is not used (it pulls in torch), only its model packages. A `<lang>->en` package is
~150 MB, so it is downloaded the first time that language shows up in chat and kept in `translate_models/`.

`ChatTranslator.on_chat` is the one bus subscriber for chat: it logs the message, then only queues; `run()` is the worker that does the work.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import ssl
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import certifi

from src.rules.bus import Event
from src.state.events import ChatChannel, ChatMessage

logger = logging.getLogger(__name__)

MODELS_DIR = Path("translate_models")
INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
TARGET = "en"


@dataclass(frozen=True)
class Detected:
    code: str  # ISO 639-1, lower case
    confidence: float


class Detector:
    """Wraps lingua, restricted to English plus the languages we can translate."""

    # Languages we detect and translate (each has an Argos `<code>->en` package; the index is the source of truth for links)
    SUPPORTED = frozenset({"ru", "es", "tl", "zh"})
    MIN_LENGTH = 8  # characters; shorter messages ("gg", "ez", "mid pls") are too little to tell the language or worth translating

    def __init__(self) -> None:
        from lingua import Language, LanguageDetectorBuilder

        wanted = [
            lang for lang in Language.all()
            if lang.iso_code_639_1.name.lower() in self.SUPPORTED | {TARGET}
        ]
        self._detector = LanguageDetectorBuilder.from_languages(*wanted).build()

    def detect(self, text: str) -> Detected | None:
        if len(text.strip()) < self.MIN_LENGTH:
            return None
        values = self._detector.compute_language_confidence_values(text)
        if not values:
            return None
        best = values[0]
        return Detected(best.language.iso_code_639_1.name.lower(), best.value)


class Model:
    """One loaded `<lang>->en` package."""

    def __init__(self, directory: Path) -> None:
        import ctranslate2
        import sentencepiece

        self._sp = sentencepiece.SentencePieceProcessor(model_file=str(directory / "sentencepiece.model"))
        self._translator = ctranslate2.Translator(str(directory / "model"), device="cpu", inter_threads=1, intra_threads=2)

    def translate(self, text: str) -> str:
        tokens = self._sp.encode(text, out_type=str)
        result = self._translator.translate_batch([tokens], beam_size=4, max_decoding_length=256)[0]
        return self._sp.decode(result.hypotheses[0]).strip()


def model_dir(code: str) -> Path:
    return MODELS_DIR / f"{code}_{TARGET}"


def model_installed(code: str) -> bool:
    d = model_dir(code)
    return (d / "sentencepiece.model").is_file() and (d / "model" / "model.bin").is_file()


def extract_package(archive: Path, dest: Path) -> None:
    """Unpack only the translation model and tokenizer from an .argosmodel (the rest is sentence-splitter data)."""
    tmp = dest.with_name(dest.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "model").mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            parts = Path(info.filename).parts
            if len(parts) == 2 and parts[1] == "sentencepiece.model":
                target = tmp / "sentencepiece.model"
            elif len(parts) == 3 and parts[1] == "model" and not info.is_dir():
                target = tmp / "model" / parts[2]
            else:
                continue
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    if not (tmp / "sentencepiece.model").is_file() or not (tmp / "model" / "model.bin").is_file():
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError("not a translation package")
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)


def _session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))
    return aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=1800))


async def download_model(code: str) -> None:
    async with _session() as session:
        async with session.get(INDEX_URL) as resp:
            resp.raise_for_status()
            index = await resp.json(content_type=None)
        links = [p["links"][0] for p in index if p["from_code"] == code and p["to_code"] == TARGET and p.get("links")]
        if not links:
            raise ValueError(f"no {code}->{TARGET} package in the Argos index")
        MODELS_DIR.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=MODELS_DIR, suffix=".argosmodel", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                async with session.get(links[0]) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.content.iter_chunked(1 << 16):
                        tmp.write(chunk)
            except BaseException:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise
    try:
        await asyncio.to_thread(extract_package, tmp_path, model_dir(code))
    finally:
        tmp_path.unlink(missing_ok=True)


def channel_name(msg: ChatMessage) -> str:
    return msg.channel.name.lower() if isinstance(msg.channel, ChatChannel) else str(msg.channel)


class ChatTranslator:
    MIN_CONFIDENCE = 0.5
    RETRY_AFTER = 600.0  # seconds before trying a failed download again
    MAX_PENDING = 5  # messages kept per language while its model downloads
    QUEUE_SIZE = 50

    def __init__(self) -> None:
        self._queue: asyncio.Queue[ChatMessage] = asyncio.Queue(self.QUEUE_SIZE)
        self._detector: Detector | None = None
        self._models: dict[str, Model] = {}
        self._downloading: dict[str, asyncio.Task] = {}
        self._pending: dict[str, list[ChatMessage]] = {}
        self._failed_at: dict[str, float] = {}

    def on_chat(self, event: Event) -> None:
        """Bus handler: log the message, then queue it for translation (never block the update)."""
        msg = event.payload
        assert isinstance(msg, ChatMessage)
        logger.info(f"Chat [{channel_name(msg)}] player {msg.player_id}: {msg.message}")
        try:
            self._queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("Chat translation is behind, dropping a message")

    async def run(self) -> None:
        try:
            self._detector = await asyncio.to_thread(Detector)
        except Exception as e:
            logger.error(f"Chat translation disabled, could not start the language detector: {e}")
            return
        while True:
            msg = await self._queue.get()
            try:
                await self._handle(msg)
            except Exception as e:
                logger.warning(f"Could not translate chat message {msg.message!r}: {e}")

    async def _handle(self, msg: ChatMessage) -> None:
        assert self._detector is not None
        found = await asyncio.to_thread(self._detector.detect, msg.message)
        if found is None or found.code == TARGET or found.confidence < self.MIN_CONFIDENCE:
            return
        await self._translate(msg, found.code)

    async def _translate(self, msg: ChatMessage, code: str) -> None:
        model = self._models.get(code)
        if model is None and model_installed(code):
            model = await asyncio.to_thread(Model, model_dir(code))
            self._models[code] = model
        if model is None:
            self._request_model(msg, code)
            return
        text = await asyncio.to_thread(model.translate, msg.message)
        logger.info(f"Chat [{channel_name(msg)}] player {msg.player_id} ({code}->{TARGET}): {text}")

    def _request_model(self, msg: ChatMessage, code: str) -> None:
        if time.monotonic() - self._failed_at.get(code, -self.RETRY_AFTER) < self.RETRY_AFTER:
            return
        pending = self._pending.setdefault(code, [])
        if len(pending) < self.MAX_PENDING:
            pending.append(msg)
        if code not in self._downloading:
            logger.info(f"Downloading the {code}->{TARGET} translation model (~150 MB, one time)")
            self._downloading[code] = asyncio.create_task(self._fetch(code), name=f"translate-{code}")

    async def _fetch(self, code: str) -> None:
        try:
            try:
                await download_model(code)
            except Exception as e:
                self._failed_at[code] = time.monotonic()
                self._pending.pop(code, None)
                logger.warning(f"Could not download the {code}->{TARGET} translation model, will retry later: {e}")
                return
            logger.info(f"Translation model {code}->{TARGET} ready")
            for msg in self._pending.pop(code, []):
                try:
                    await self._translate(msg, code)
                except Exception as e:
                    logger.warning(f"Could not translate chat message {msg.message!r}: {e}")
        finally:
            self._downloading.pop(code, None)
