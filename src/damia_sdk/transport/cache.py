"""Ограниченный по размеру асинхронный кеш транспортных ответов."""

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace

from damia_sdk.settings import CacheSettings
from damia_sdk.transport.response import HttpResponse


class _MemoryBackend:
    """In-memory commit checks permission without yielding before mutation."""

    def __init__(self) -> None:
        self._values: dict[str, HttpResponse] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}

    def _delete(self, key: str) -> int:
        value = self._values.pop(key, None)
        timer = self._timers.pop(key, None)
        if timer is not None:
            timer.cancel()
        return int(value is not None)

    async def get(self, key: str) -> HttpResponse | None:
        return self._values.get(key)

    async def set(
        self,
        key: str,
        value: HttpResponse,
        *,
        ttl: float | None,
        permitted: Callable[[], bool] | None,
    ) -> bool:
        if permitted is not None and not permitted():
            return False
        self._delete(key)
        self._values[key] = value
        if ttl:
            self._timers[key] = asyncio.get_running_loop().call_later(
                ttl, self._delete, key
            )
        return True

    async def delete(self, key: str) -> int:
        return self._delete(key)

    async def close(self) -> None:
        pass


class ResponseCache:
    """Локальный TTL-кеш; ошибки удаления могут временно занимать память."""

    def __init__(self, settings: CacheSettings) -> None:
        self._settings = settings
        self._cache = _MemoryBackend()
        self._keys: OrderedDict[str, None] = OrderedDict()
        self._pending: set[str] = set()
        self._generation = 0
        self._lock = asyncio.Lock()
        self._backend_closed = False

    def _physical_key(self, key: str) -> str:
        return f"{self._generation}:{key}"

    async def generation(self) -> int:
        async with self._lock:
            return self._generation

    async def get(self, key: str) -> HttpResponse | None:
        async with self._lock:
            physical = self._physical_key(key)
            if physical not in self._keys:
                return None
            try:
                result = await self._cache.get(physical)
            except Exception:  # noqa: BLE001
                return None
            if not isinstance(result, HttpResponse):
                self._keys.pop(physical, None)
                return None
            self._keys.move_to_end(physical)
            return replace(result, from_cache=True)

    async def set(
        self,
        key: str,
        response: HttpResponse,
        *,
        ttl: float | None = None,
        generation: int | None = None,
        permitted: Callable[[], bool] | None = None,
    ) -> None:
        if len(response.body) > self._settings.max_entry_bytes:
            return
        async with self._lock:
            if (generation is not None and generation != self._generation) or (
                permitted is not None and not permitted()
            ):
                return
            physical = self._physical_key(key)
            try:
                if (
                    physical not in self._keys
                    and len(self._keys) >= self._settings.max_entries
                ):
                    expired = []
                    for indexed in self._keys:
                        if await self._cache.get(indexed) is None:
                            expired.append(indexed)
                    for indexed in expired:
                        self._keys.pop(indexed)
                while (
                    physical not in self._keys
                    and len(self._keys) >= self._settings.max_entries
                ):
                    old, _ = self._keys.popitem(last=False)
                    self._pending.add(old)
                    await self._cache.delete(old)
                    self._pending.discard(old)
                # Track before awaiting: cancellation may occur after backend writes.
                was_pending = physical in self._pending
                self._pending.add(physical)
                committed = await self._cache.set(
                    physical,
                    response,
                    ttl=self._settings.ttl if ttl is None else ttl,
                    permitted=permitted,
                )
                if committed or not was_pending:
                    self._pending.discard(physical)
                if not committed:
                    return
                self._keys[physical] = None
                self._keys.move_to_end(physical)
            except Exception:  # noqa: BLE001
                self._keys.pop(physical, None)

    async def clear(self) -> None:
        """Инвалидировать сразу; неудачные удаления повторяются при следующей очистке."""
        async with self._lock:
            self._generation += 1
            self._pending.update(self._keys)
            self._keys.clear()
            failed = False
            for key in tuple(self._pending):
                try:
                    await self._cache.delete(key)
                except Exception:  # noqa: BLE001
                    failed = True
                else:
                    self._pending.discard(key)
            if failed:
                raise RuntimeError("Не удалось очистить кеш.")

    async def close(self) -> None:
        """Очистить кеш и закрыть backend, повторяя неудачные операции."""
        failed = False
        try:
            try:
                await self.clear()
            except Exception:  # noqa: BLE001
                failed = True
        finally:
            if not self._backend_closed:
                try:
                    await self._cache.close()
                except Exception:  # noqa: BLE001
                    failed = True
                else:
                    self._backend_closed = True
        if failed:
            raise RuntimeError("Не удалось освободить кеш.")
