from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Coroutine
from typing import Any

from src.media import resolve
from src.rules.actions.base import ActionBinding, ActionExecutor, describe
from src.rules.actions.drop_filter import DropFilter
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
        self._filter_settings = (0.0, 0.0)
        self._filter = DropFilter(*self._filter_settings)

    def configure_filter(self, drop_ratio: float, min_interval: float) -> None:
        """Set the soundboard chattiness. Learned state restarts only when the numbers change."""
        if (drop_ratio, min_interval) != self._filter_settings:
            self._filter_settings = (drop_ratio, min_interval)
            self._filter = DropFilter(drop_ratio, min_interval)

    def on_event(self, event: Event) -> None:
        """Queue every sound bound to the event's key on STARTED; ENDED is ignored."""
        if event.type is not EventType.STARTED or event.initial:
            return  # an initial event is a state already true on first look, not something that just happened
        for binding in self._bindings.get(event.key, []):
            self._queue.put_nowait((binding, event))

    def workers(self) -> dict[str, Coroutine[Any, Any, None]]:
        """The queue-draining coroutine that plays the sounds."""
        return {"action_sound": self._drain(), "drop_filter_dump": self._dump_filter()}

    DUMP_INTERVAL = 5  # seconds between drop filter state dumps

    async def _dump_filter(self) -> None:
        """Log the drop filter's state every DUMP_INTERVAL seconds while it is active."""
        while True:
            await asyncio.sleep(self.DUMP_INTERVAL)
            if self._filter_settings[0] > 0 and self._filter_settings[1] > 0:
                logger.info(f"Drop filter: {self._filter.dump()}")

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
                if not self._filter.should_allow(binding.rule_id):
                    logger.info(f"{describe(binding, event)} -> {binding.action.type} dropped (chattiness)")
                    continue
                logger.info(f"{describe(binding, event)} -> {binding.action.type}")
                try:
                    await self._play(binding.action)
                except Exception:
                    # A bad file or audio device error must not kill the worker for the rest of the session
                    logger.exception(f"Sound failed for rule {binding.rule_id!r}")

    async def _play(self, action: PlaySoundAction) -> None:
        clip = random.choices(action.clips, weights=[c.probability for c in action.clips])[0]
        path = resolve(clip.file)
        if not path.is_file():
            logger.warning(f"Sound file not found, skipping: {path}")
            return
        await self._sound.play(str(path), volume=clip.volume / 100)
