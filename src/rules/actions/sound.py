from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Coroutine
from typing import Any

from src.rules.actions.base import ActionBinding, ActionExecutor, describe
from src.rules.bus import Event, EventType
from src.rules.config import ActionType, PlaySoundAction
from src.sound import SoundManager

logger = logging.getLogger(__name__)


class SoundExecutor(ActionExecutor[PlaySoundAction]):
    action_type = ActionType.PLAY_SOUND

    BURST_LIMIT = 3  # this many sounds from one game update are treated as a burst and dropped

    def __init__(self, sound: SoundManager) -> None:
        super().__init__()
        self._sound = sound
        self._queue: asyncio.Queue[tuple[ActionBinding[PlaySoundAction], Event]] = asyncio.Queue()

    def on_event(self, event: Event) -> None:
        """Queue every sound bound to the event's key on STARTED; ENDED is ignored."""
        if event.type is not EventType.STARTED:
            return
        for binding in self._bindings.get(event.key, []):
            self._queue.put_nowait((binding, event))

    def workers(self) -> dict[str, Coroutine[Any, Any, None]]:
        """The queue-draining coroutine that plays the sounds."""
        return {"action_sound": self._drain()}

    async def _drain(self) -> None:
        """Sounds queued together, BURST_LIMIT or more, are dropped.

        That many at once is the state already true when a monitor first looks (starting items,
        day/night, ...), e.g. at match start or after a rules reload, and playing them overlaps
        into noise. Updates are processed synchronously, so a burst is all in the queue together.
        """
        while True:
            batch = [await self._queue.get()]
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            if len(batch) >= self.BURST_LIMIT:
                logger.warning(
                    f"Dropped {len(batch)} sounds fired at once: " + ", ".join(b.rule_id for b, _ in batch)
                )
                continue
            for binding, event in batch:
                logger.info(f"{describe(binding, event)} -> {binding.action.type}")
                try:
                    await self._play(binding.action)
                except Exception:
                    # A bad file or audio device error must not kill the worker for the rest of the session
                    logger.exception(f"Sound failed for rule {binding.rule_id!r}")

    async def _play(self, action: PlaySoundAction) -> None:
        clip = random.choices(action.clips, weights=[c.probability for c in action.clips])[0]
        await self._sound.play(clip.file, volume=clip.volume / 100)
