from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

import aiohttp

from src.rules.bus import EventContext, QueuedAction, RuleEventBus
from src.rules.config import (
    ActionType,
    AnyAction,
    PlaySoundAction,
    WebhookAction,
)
from src.sound import SoundManager

logger = logging.getLogger(__name__)


class ActionExecutor:
    """One worker coroutine per action type, each draining its own queue.

    Params are validated at config load — no validation here.
    """

    BURST_LIMIT = 3  # this many sounds from one game update are treated as a burst and dropped

    def __init__(
        self,
        sound: SoundManager,
    ) -> None:
        self._sound = sound
        self._webhook_last_fired: dict[int, float] = {}
        self._webhook_tasks: set[asyncio.Task[None]] = set()
        self._handlers: dict[ActionType, Callable[[Any, EventContext], Awaitable[None]]] = {
            ActionType.PLAY_SOUND:        self._execute_play_sound,
            ActionType.WEBHOOK:           self._execute_webhook,
        }

    def worker_coroutines(self, bus: RuleEventBus) -> dict[str, Any]:
        """Return one named coroutine per action type queue."""
        return {
            "action_sound":   self._drain_sounds(bus.queue_for(ActionType.PLAY_SOUND)),
            "action_webhook": self._drain(bus.queue_for(ActionType.WEBHOOK)),
        }

    async def _drain(self, queue: asyncio.Queue[QueuedAction]) -> None:
        while True:
            item = await queue.get()
            if item.action.enabled:
                await self._dispatch(item.action, item.ctx)
            queue.task_done()

    async def _drain_sounds(self, queue: asyncio.Queue[QueuedAction]) -> None:
        """Like _drain, but sounds queued together, BURST_LIMIT or more, are dropped.

        That many at once is the state already true when a monitor first looks (starting items,
        day/night, ...), e.g. at match start or after a rules reload, and playing them overlaps
        into noise. Updates are processed synchronously, so a burst is all in the queue together.
        """
        while True:
            first = await queue.get()
            batch = [first] if first.action.enabled else []
            while not queue.empty():
                item = queue.get_nowait()
                if item.action.enabled:
                    batch.append(item)
            if len(batch) >= self.BURST_LIMIT:
                logger.warning(
                    f"Dropped {len(batch)} sounds fired at once: " + ", ".join(q.ctx.rule_id for q in batch)
                )
            else:
                for q in batch:
                    await self._dispatch(q.action, q.ctx)

    async def _dispatch(self, action: AnyAction, ctx: EventContext) -> None:
        logger.info(f"{ctx} -> {action.type}")
        if handler := self._handlers.get(action.type):
            await handler(action, ctx)

    async def _execute_play_sound(self, action: PlaySoundAction, ctx: EventContext) -> None:
        clip = random.choices(action.clips, weights=[c.probability for c in action.clips])[0]
        await self._sound.play(clip.file, volume=clip.volume / 100)

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
        "game_time": ctx.game_time,
        "clock_time": ctx.clock_time,
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
