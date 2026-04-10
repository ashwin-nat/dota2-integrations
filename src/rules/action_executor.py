from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

import aiohttp

from src.lighting.controller import LightingController
from src.rules.bus import EventContext
from src.rules.config import (
    ActionType,
    AnyAction,
    LightAction,
    LoggerAction,
    MapColours,
    PlaySoundAction,
    WebhookAction,
)
from src.sound import SoundManager

if TYPE_CHECKING:
    from src.state.map import MapState

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Dispatches typed Action models to the appropriate subsystems.

    Params are validated at config load — no validation here.
    """

    def __init__(
        self,
        sound: SoundManager,
        lighting: LightingController,
        map_colours: MapColours | None = None,
        get_map: Callable[[], MapState | None] | None = None,
    ) -> None:
        self._sound = sound
        self._lighting = lighting
        self._map_colours = map_colours
        self._get_map = get_map
        self._webhook_last_fired: dict[int, float] = {}  # id(action) → last fire time
        self._webhook_tasks: set[asyncio.Task[None]] = set()

        self._dispatch = {
            ActionType.PLAY_SOUND:  self._execute_play_sound,
            ActionType.LIGHT:       self._execute_light,
            ActionType.RESET_LIGHT: self._execute_reset_light,
            ActionType.LOGGER:      self._execute_logger,
            ActionType.WEBHOOK:     self._execute_webhook,
        }

    async def execute(self, actions: list[AnyAction], ctx: EventContext) -> None:
        for action in actions:
            if action.type == ActionType.WEBHOOK:
                await self._execute_webhook(action, ctx)  # type: ignore[arg-type]
            else:
                await self._dispatch[action.type](action)  # type: ignore[arg-type]

    async def _execute_play_sound(self, action: PlaySoundAction) -> None:
        await self._sound.play(action.file, volume=action.volume / 100)

    async def _execute_light(self, action: LightAction) -> None:
        await self._lighting.set_colour_rgb(action.r, action.g, action.b)

    async def _execute_reset_light(self, _action: AnyAction) -> None:
        if self._map_colours is None or self._get_map is None:
            return
        map_state = self._get_map()
        if map_state is None:
            return
        colour = self._map_colours.day if map_state.daytime else self._map_colours.night
        await self._lighting.set_colour_rgb(colour.r, colour.g, colour.b)

    async def _execute_logger(self, action: LoggerAction) -> None:
        print(f"[logger] {action.message}")

    async def _execute_webhook(self, action: WebhookAction, ctx: EventContext) -> None:
        key = id(action)
        now = time.monotonic()
        if action.cooldown > 0:
            last = self._webhook_last_fired.get(key, 0.0)
            if now - last < action.cooldown:
                return
        self._webhook_last_fired[key] = now
        task = asyncio.create_task(_fire_webhook(action, ctx))
        self._webhook_tasks.add(task)
        task.add_done_callback(self._webhook_tasks.discard)


def _build_url(action: WebhookAction) -> str:
    if action.auth_type != "query" or action.api_key is None:
        return action.url
    parsed = urlparse(action.url)
    existing = parse_qs(parsed.query, keep_blank_values=True)
    existing["api_key"] = [action.api_key]
    new_query = urlencode({k: v[0] for k, v in existing.items()})
    return urlunparse(parsed._replace(query=new_query))


def _build_headers(action: WebhookAction) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if action.api_key is None or action.auth_type is None:
        return headers
    if action.auth_type == "bearer":
        headers["Authorization"] = f"Bearer {action.api_key}"
    elif action.auth_type == "header":
        headers["X-API-Key"] = action.api_key
    return headers


async def _fire_webhook(action: WebhookAction, ctx: EventContext) -> None:
    url = _build_url(action)
    headers = _build_headers(action)
    payload = {
        "version": 1,
        "event": ctx.event_name,
        "rule_id": ctx.rule_id,
        "monitor_type": ctx.monitor_type,
        "timestamp": time.time(),
        "data": ctx.data,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=action.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if not resp.ok:
                    logger.warning(
                        "webhook %s returned HTTP %d for rule %r",
                        url, resp.status, ctx.rule_id,
                    )
    except Exception as exc:
        logger.warning("webhook %s failed for rule %r: %s", url, ctx.rule_id, exc)
