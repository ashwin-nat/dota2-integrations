from __future__ import annotations

import asyncio
from typing import Dict

import pygame.mixer


class SoundManager:
    def __init__(self, *, max_channels: int = 16, default_volume: float = 1.0) -> None:
        pygame.mixer.init()
        pygame.mixer.set_num_channels(max_channels)
        self._default_volume = default_volume
        self._cache: Dict[str, pygame.mixer.Sound] = {}
        self._loading: Dict[str, asyncio.Future[pygame.mixer.Sound]] = {}
        self._loop = asyncio.get_event_loop()

    async def play(self, path: str, *, volume: float | None = None) -> None:
        sound = await self._load(path)
        channel = sound.play()
        if channel is not None:
            channel.set_volume(volume if volume is not None else self._default_volume)

    async def _load(self, path: str) -> pygame.mixer.Sound:
        if path in self._cache:
            return self._cache[path]

        if path in self._loading:
            return await asyncio.shield(self._loading[path])

        future: asyncio.Future[pygame.mixer.Sound] = self._loop.create_future()
        self._loading[path] = future

        try:
            sound = await self._loop.run_in_executor(
                None, pygame.mixer.Sound, path
            )
            self._cache[path] = sound
            future.set_result(sound)
            return sound
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            self._loading.pop(path, None)
