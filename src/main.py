import asyncio
from pathlib import Path

RULES_PATH = Path("rules.json")

from src.ingress.http_server import serve
from src.lighting import load_lighting_controller
from src.rules import compile_rules, RulesConfig
from src.rules.action_executor import ActionExecutor
from src.rules.bus import RuleEventBus
from src.sound import SoundManager
from src.state.store import GameState


def _exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    exc = context.get("exception")
    msg = context.get("message", "")
    # Suppress debugger-induced noise: pausing execution leaves the socket in a
    # state where IOCP accept() fails with WinError 64, and aiohttp's
    # _request_factory is None because the handler hasn't resumed yet.
    if isinstance(exc, OSError) and exc.winerror == 64:
        return
    if isinstance(exc, TypeError) and "'NoneType' object is not callable" in str(exc):
        return
    if "Accept failed on a socket" in msg:
        return
    loop.default_exception_handler(context)


async def main() -> None:
    asyncio.get_event_loop().set_exception_handler(_exception_handler)

    rules_config = RulesConfig.load(RULES_PATH)
    lighting = load_lighting_controller(rules_config.lighting.vendor, enabled=rules_config.lighting.enabled)
    await lighting.setup()

    queue: asyncio.Queue[dict] = asyncio.Queue()
    state = GameState()

    # --- Rule engine setup ---
    sound = SoundManager(default_volume=rules_config.sound.volume / 100)
    executor = ActionExecutor(
        sound, lighting,
        map_colours=rules_config.map_colours,
        get_map=lambda: state.map,
    )
    rule_bus = RuleEventBus(executor.execute)
    compiled = compile_rules(rules_config.rules, rule_bus)
    state.set_compiled_rules(compiled)
    n_monitors = len(compiled.item_monitors) + len(compiled.map_monitors) + len(compiled.hero_monitors)
    print(f"Rule engine ready: {n_monitors} monitors ({len(compiled.item_monitors)} item, {len(compiled.map_monitors)} map, {len(compiled.hero_monitors)} hero), {len(executor._dispatch)} executor dispatch handlers")
    # -------------------------

    async def ingest() -> None:
        while True:
            data = await queue.get()
            state.set(data)

    tasks = [
        asyncio.create_task(ingest()),
        asyncio.create_task(rule_bus.process_forever()),
        asyncio.create_task(serve(queue)),
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
