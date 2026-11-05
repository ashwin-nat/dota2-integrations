from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import aiohttp

from src.rules.actions.base import ActionBinding, ActionExecutor, describe
from src.rules.bus import Event, EventType
from src.rules.config import ActionType, WebhookAction

logger = logging.getLogger(__name__)


class WebhookExecutor(ActionExecutor[WebhookAction]):
    action_type = ActionType.WEBHOOK

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[tuple[ActionBinding[WebhookAction], Event]] = asyncio.Queue()
        self._last_fired: dict[int, float] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def on_event(self, event: Event) -> None:
        """Queue every webhook bound to the event's key on STARTED; ENDED is ignored."""
        if event.type is not EventType.STARTED:
            return
        for binding in self._bindings.get(event.key, []):
            self._queue.put_nowait((binding, event))

    def workers(self) -> dict[str, Coroutine[Any, Any, None]]:
        """The queue-draining coroutine that fires the webhooks (cooldown applied, POST in its own task)."""
        return {"action_webhook": self._drain()}

    async def _drain(self) -> None:
        while True:
            binding, event = await self._queue.get()
            try:
                logger.info(f"{describe(binding, event)} -> {binding.action.type}")
                self._fire(binding, event)
            except Exception:
                # One bad webhook must not kill the worker for the rest of the session
                logger.exception(f"Webhook failed for rule {binding.rule_id!r}")
            finally:
                self._queue.task_done()

    def _fire(self, binding: ActionBinding[WebhookAction], event: Event) -> None:
        action = binding.action
        key = id(action)
        now = time.monotonic()
        if action.cooldown > 0 and now - self._last_fired.get(key, 0.0) < action.cooldown:
            return
        self._last_fired[key] = now
        task = asyncio.create_task(_post_webhook(binding, event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


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


async def _post_webhook(binding: ActionBinding[WebhookAction], event: Event) -> None:
    action = binding.action
    url = _build_url(action)
    payload = {
        "version": 1,
        "event": binding.event_name,
        "rule_id": binding.rule_id,
        "monitor_type": binding.monitor_type,
        "timestamp": time.time(),
        "game_time": event.game_time,
        "clock_time": event.clock_time,
        "data": {},
    }
    try:
        timeout = aiohttp.ClientTimeout(total=action.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=_build_headers(action)) as resp:
                if not resp.ok:
                    logger.warning("webhook %s returned HTTP %d for rule %r", url, resp.status, binding.rule_id)
    except Exception as exc:
        logger.warning("webhook %s failed for rule %r: %s", url, binding.rule_id, exc)
