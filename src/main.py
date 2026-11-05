import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import aiofiles
from pydantic import ValidationError

RULES_PATH = Path("rules.json")

from src.ingress.http_server import serve
from src.lighting import load_lighting_controller
from src.lighting.arbiter import LightingArbiter
from src.log_setup import setup_logging
from src.recorder import Recorder
from src.rules import RulesConfig, compile_rules
from src.rules.actions import (ActionExecutor, LightExecutor, SoundExecutor,
                               WebhookExecutor)
from src.rules.bus import EventBus
from src.sound import SoundManager
from src.state.store import GameState

logger = logging.getLogger(__name__)


def _exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    exc = context.get("exception")
    msg = context.get("message", "")
    # Suppress debugger-induced noise: pausing execution leaves the socket in a
    # state where IOCP accept() fails with WinError 64, and aiohttp's
    # _request_factory is None because the handler hasn't resumed yet.
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 64:
        return
    if isinstance(exc, TypeError) and "'NoneType' object is not callable" in str(exc):
        return
    if "Accept failed on a socket" in msg:
        return
    loop.default_exception_handler(context)


DEBUG_EVENT_HISTORY = 100


async def main(record: bool = False, debug: bool = False) -> None:
    asyncio.get_event_loop().set_exception_handler(_exception_handler)

    try:
        rules_config = RulesConfig.load(RULES_PATH)
    except ValidationError as e:
        for err in e.errors():
            logger.error(f"rules.json: {err['msg'].removeprefix('Value error, ')}")
        logger.error("Fix or remove those rules in rules.json, then start again")
        raise SystemExit(1)
    lighting = load_lighting_controller(rules_config.lighting.vendor, enabled=rules_config.lighting.enabled)
    await lighting.setup()

    queue: asyncio.Queue[dict] = asyncio.Queue()

    # --- Rule engine setup ---
    sound = SoundManager(default_volume=rules_config.sound.volume / 100)
    arbiter = LightingArbiter(lighting)
    executors: list[ActionExecutor] = [LightExecutor(arbiter), SoundExecutor(sound), WebhookExecutor()]
    bus = EventBus(history_size=DEBUG_EVENT_HISTORY if debug else 0)
    compiled = compile_rules(rules_config.rules, bus, {e.action_type: e for e in executors})
    state = GameState(compiled, bus, arbiter)
    counts = ", ".join(f"{n} {t}" for t, n in compiled.counts().items())
    logger.info(f"Rule engine ready: {len(compiled.monitors)} monitors ({counts})")
    # -------------------------

    async def ingest() -> None:
        while True:
            data = await queue.get()
            try:
                state.update(data)
            except Exception as e:
                timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S_%f")
                file_name = f"error_dump_{timestamp}.json"
                async with aiofiles.open(file_name, "w") as f:
                    await f.write(json.dumps(data, indent=2))
                logger.exception(f"Error processing update: {e} \n Dumped data to {file_name}")
            finally:
                queue.task_done()

    recorder = Recorder() if record else None
    if recorder is not None:
        logger.info("Record mode on: POST/GET http://127.0.0.1:6969/record/save writes the history to recordings/")

    tasks = [
        asyncio.create_task(ingest(), name="ingest"),
        asyncio.create_task(arbiter.run(), name="lighting"),
        *[
            asyncio.create_task(coro, name=name)
            for executor in executors
            for name, coro in executor.workers().items()
        ],
        asyncio.create_task(serve(queue, recorder, state), name="http_server"),
    ]

    for task in tasks:
        logger.info(f"Registered task: {task.get_name()}")
    await asyncio.gather(*tasks)


def _enter_macos_app_dir() -> None:
    """A Finder-launched .app starts in `/`, so keep rules.json, configs and logs in Application Support."""
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        app_dir = Path.home() / "Library" / "Application Support" / "dota2-integrations"
        app_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(app_dir)


if __name__ == "__main__":
    _enter_macos_app_dir()
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="keep recent rule events in memory so /state (and the replay stepper) can show them")
    parser.add_argument("--record", action="store_true", help="keep incoming payloads in memory; /record/save writes them to recordings/*.jsonl")
    args = parser.parse_args()
    setup_logging()
    asyncio.run(main(record=args.record, debug=args.debug))
