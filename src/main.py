import argparse
import asyncio
import json
import logging
import threading
import urllib.request
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable

import aiofiles

RULES_PATH = Path("rules.json")

from src import dota_setup, packs, sharing, tray
from src.config_ui import setup_config_ui
from src.ingress.http_server import BASE_URL, PORT, PortInUse, serve
from src.lighting.arbiter import LightingArbiter
from src.lighting import load_lighting_controller
from src.log_setup import setup_logging
from src.recorder import Recorder
from src.rules import compile_rules, RulesConfig
from src.rules.action_executor import ActionExecutor
from src.rules.bus import RuleEventBus
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


async def main(record: bool = False, on_stop: Callable[[Callable[[], None]], None] | None = None) -> None:
    asyncio.get_event_loop().set_exception_handler(_exception_handler)

    sharing.load()
    rules_config = RulesConfig.load(RULES_PATH)
    lighting = load_lighting_controller(rules_config.lighting.vendor, enabled=rules_config.lighting.enabled)
    await lighting.setup()

    queue: asyncio.Queue[dict] = asyncio.Queue()
    # Set by the editor's power button, or the tray icon's Quit (from its own thread)
    stop = asyncio.Event()
    if on_stop:
        loop = asyncio.get_running_loop()
        def request_stop() -> None:
            if not loop.is_closed():
                loop.call_soon_threadsafe(stop.set)
        on_stop(request_stop)

    # --- Rule engine setup ---
    sound = SoundManager(default_volume=rules_config.sound.volume / 100)
    executor = ActionExecutor(sound)
    arbiter = LightingArbiter(lighting)
    rule_bus = RuleEventBus(arbiter)
    compiled = compile_rules(rules_config.rules + sharing.followed_rules(rules_config.rules), rule_bus)
    state = GameState(compiled, rule_bus, arbiter)
    n_monitors = len(compiled.item_monitors) + len(compiled.map_monitors) + len(compiled.hero_monitors) + len(compiled.ability_monitors)
    logger.info(f"Rule engine ready: {n_monitors} monitors ({len(compiled.item_monitors)} item, {len(compiled.map_monitors)} map, {len(compiled.hero_monitors)} hero, {len(compiled.ability_monitors)} ability)")
    # -------------------------

    def reload_rules(config: RulesConfig) -> bool:
        """Recompile rules saved from the editor. Returns True if a restart is still needed."""
        rule_bus.reset()
        arbiter.clear_all()
        # Sounds from friends you follow fill in triggers your own rules don't cover
        state.set_compiled_rules(compile_rules(config.rules + sharing.followed_rules(config.rules), rule_bus))
        sound.set_default_volume(config.sound.volume / 100)
        # The lighting driver is built once at startup
        return config.lighting != rules_config.lighting

    async def watch_friends() -> None:
        """Recompile when a followed friend's rules arrive through the sync service."""
        seen = sharing.followed_signature()
        while True:
            await asyncio.sleep(5)
            current = await asyncio.to_thread(sharing.followed_signature)
            if current != seen:
                seen = current
                logger.info("A followed friend's rules changed; reloading")
                try:
                    reload_rules(RulesConfig.load(RULES_PATH))
                except Exception as e:
                    # Ending this task would shut the app down
                    logger.warning(f"Could not reload rules: {e}")

    async def publish_library() -> None:
        """Keep the shared folder's library .zip current, for friends who only have its link."""
        while True:
            folder = sharing.shared_folder()
            if folder:
                try:
                    await asyncio.wait_for(asyncio.to_thread(packs.write_library, folder), timeout=300)
                except Exception as e:
                    logger.warning(f"Could not update the shared library: {e}")
            await asyncio.sleep(30)

    async def refresh_packs() -> None:
        """Pick up new versions of packs imported from a link (watch_friends then reloads)."""
        while True:
            # A build made for a group comes with its library link: fetch it on first run
            if (link := packs.default_library_link()) and not sharing.shared_folder() and not any(p.get("source") == link for p in packs.list_packs()):
                try:
                    record = await asyncio.to_thread(packs.import_pack, await packs.download(link), link)
                    sharing.set_following(f"{sharing.PACK_PREFIX}{record['id']}", True)
                    logger.info(f"Fetched the built-in library {record['name']!r}")
                except Exception as e:
                    logger.warning(f"Could not fetch the built-in library (will retry): {e}")
            for pack in packs.list_packs():
                if not pack.get("source"):
                    continue
                try:
                    if await packs.refresh(pack):
                        logger.info(f"Pack {pack['name']!r} updated from its link")
                except Exception as e:
                    logger.warning(f"Could not check pack {pack['name']!r} for updates: {e}")
            await asyncio.sleep(30 * 60)

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
        asyncio.create_task(watch_friends(), name="friends"),
        asyncio.create_task(refresh_packs(), name="packs"),
        asyncio.create_task(publish_library(), name="library"),
        *[
            asyncio.create_task(coro, name=name)
            for name, coro in executor.worker_coroutines(rule_bus).items()
        ],
        asyncio.create_task(
            serve(
                queue,
                lambda app: setup_config_ui(app, RULES_PATH, reload_rules, sound, shutdown=stop.set),
                on_started=_open_editor,
                recorder=recorder,
                state=state,
                rule_bus=rule_bus,
            ),
            name="http_server",
        ),
    ]

    sharing.publish_safely()
    if getattr(sys, "frozen", False) or not os.environ.get("GSI_PORT"):
        # Not for dev/test instances on other ports: they'd add configs to the real Dota
        await asyncio.to_thread(dota_setup.install_gsi_config, PORT)
    for task in tasks:
        logger.info(f"Registered task: {task.get_name()}")
    stopper = asyncio.create_task(stop.wait(), name="shutdown")
    done, _ = await asyncio.wait([*tasks, stopper], return_when=asyncio.FIRST_COMPLETED)
    # Cancelling the server task closes the port before the process exits
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    for task in done:
        if task is not stopper and not task.cancelled() and task.exception():
            raise task.exception()  # type: ignore[misc]
    logger.info("Shut down")


def _open_editor(base_url: str, force: bool = False) -> None:
    """Open the rules editor in the default browser; the packaged app has no window of its own."""
    if not force and ("--no-browser" in sys.argv or os.environ.get("GSI_NO_BROWSER")):
        return
    try:
        webbrowser.open(f"{base_url}/ui")
    except Exception as e:
        logger.warning(f"Could not open browser: {e}")


def _app_already_running() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/info", timeout=2) as resp:
            return "data_dir" in json.loads(resp.read())
    except Exception:
        return False


APP_DIR_NAME = "Juke"
OLD_APP_DIR_NAME = "dota2-integrations"


def _enter_app_dir() -> None:
    """Keep rules.json, sounds, configs and logs in the user's app data folder in the packaged app.

    A Finder-launched .app starts in `/`, and a downloaded .exe would litter Downloads.
    An older Windows install with rules.json beside the .exe keeps using that folder.
    """
    if not getattr(sys, "frozen", False):
        return
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        if (Path(sys.executable).parent / "rules.json").exists():
            os.chdir(Path(sys.executable).parent)
            return
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        return
    app_dir = base / APP_DIR_NAME
    old_dir = base / OLD_APP_DIR_NAME
    if not app_dir.exists() and old_dir.is_dir():
        # The app used to be called dota2-integrations: keep everyone's rules, sounds and settings
        try:
            old_dir.rename(app_dir)
        except OSError:
            app_dir = old_dir  # e.g. a file in it is open elsewhere; try again next launch
    app_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(app_dir)


def _run_with_tray(record: bool) -> None:
    """Run the app in a background thread and the tray icon on the main thread until either quits."""
    stoppers: list = []
    failure: list[BaseException] = []
    icon = tray.make_icon(lambda: _open_editor(BASE_URL, force=True), lambda: stoppers and stoppers[0]())
    if icon is None:
        asyncio.run(main(record=record))
        return

    def app() -> None:
        try:
            asyncio.run(main(record=record, on_stop=stoppers.append))
        except BaseException as e:
            failure.append(e)
        finally:
            icon.stop()

    worker = threading.Thread(target=app, name="app")
    worker.start()
    icon.run()
    # Quit from the icon (or the Dock): let the app close its port before exiting
    if stoppers and worker.is_alive():
        stoppers[0]()
    worker.join(timeout=10)
    if failure:
        raise failure[0]


if __name__ == "__main__":
    # A windowed Windows build has no console: give libraries that print (yt-dlp, pygame) somewhere to write
    if sys.stdout is None or sys.stderr is None:
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    _enter_app_dir()
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="keep incoming payloads in memory; /record/save writes them to recordings/*.jsonl")
    parser.add_argument("--no-browser", action="store_true", help="do not open the rules editor in the browser")
    parser.add_argument("--tray", action=argparse.BooleanOptionalAction, default=getattr(sys, "frozen", False),
                        help="show a menu bar / tray icon (default in the packaged app)")
    args = parser.parse_args()
    setup_logging()
    try:
        if args.tray:
            _run_with_tray(args.record)
        else:
            asyncio.run(main(record=args.record))
    except PortInUse:
        # Double-clicking the app again is the usual cause: show the running one instead
        if _app_already_running():
            logger.info(f"Juke is already running at {BASE_URL}; opening its editor")
            _open_editor(BASE_URL, force=True)
            sys.exit(0)
        logger.error(
            f"Port {PORT} is used by another program. Close it, or set GSI_PORT to a free port "
            "(and change the port in Dota's gamestate_integration config to match)."
        )
        sys.exit(1)
