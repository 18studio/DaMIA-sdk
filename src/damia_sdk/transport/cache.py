"""Ограниченный по размеру асинхронный кеш транспортных ответов."""

import asyncio
from collections import OrderedDict
from dataclasses import replace

from aiocache import SimpleMemoryCache  # type: ignore[import-untyped]

from damia_sdk.settings import CacheSettings
from damia_sdk.transport.response import HttpResponse


class ResponseCache:
    """Локальный TTL-кеш; ключи должны быть непрозрачными дайджестами."""

    def __init__(self, settings: CacheSettings) -> None:
        self._settings = settings
        self._cache = SimpleMemoryCache()
        self._keys: OrderedDict[str, None] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> HttpResponse | None:
        async with self._lock:
            try:
                result = await self._cache.get(key)
            except Exception:  # noqa: BLE001
                # Сбой кеша не должен блокировать запрос; отмена задачи не подавляется.
                return None
            if not isinstance(result, HttpResponse):
                self._keys.pop(key, None)
                return None
            self._keys[key] = None
            self._keys.move_to_end(key)
            return replace(result, from_cache=True)

    async def set(
        self, key: str, response: HttpResponse, *, ttl: float | None = None
    ) -> None:
        if len(response.body) > self._settings.max_entry_bytes:
            return
        async with self._lock:
            try:
                while (
                    key not in self._keys
                    and len(self._keys) >= self._settings.max_entries
                ):
                    old, _ = self._keys.popitem(last=False)
                    await self._cache.delete(old)
                await self._cache.set(
                    key, response, ttl=self._settings.ttl if ttl is None else ttl
                )
                self._keys[key] = None
                self._keys.move_to_end(key)
            except Exception:  # noqa: BLE001
                # Кеширование — необязательная оптимизация.
                self._keys.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            # delete отменяет таймеры TTL в aiocache 0.12, в отличие от clear().
            try:
                for key in self._keys:
                    await self._cache.delete(key)
            finally:
                self._keys.clear()

    async def close(self) -> None:
        await self.clear()
        await self._cache.close()
