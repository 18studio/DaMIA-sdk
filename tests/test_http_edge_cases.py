"""Граничные сценарии повторов, кеширования и безопасного закрытия."""

import asyncio
import traceback

import httpx
import pytest
from pydantic import SecretStr
from tenacity import AsyncRetrying

from damia_sdk import (
    BaseURLSettings,
    CacheSettings,
    DamiaConfigurationError,
    DamiaConnectionError,
    DamiaHTTPError,
    DamiaSettings,
    DamiaTimeoutError,
    RetrySettings,
)
from damia_sdk.transport import HttpClient, HttpResponse


def settings(
    *, cache: CacheSettings | None = None, retry: RetrySettings | None = None
) -> DamiaSettings:
    return DamiaSettings(
        fns_key=SecretStr("test-secret"),
        base_urls=BaseURLSettings(fns="http://127.0.0.1:4010"),
        cache=cache or CacheSettings(),
        retry=retry or RetrySettings(),
    )


def test_settings_read_nested_core_configuration_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DAMIA_API_KEY", "synthetic-shared")
    monkeypatch.setenv("DAMIA_CACHE__ENABLED", "true")
    monkeypatch.setenv("DAMIA_CACHE__TTL", "12")
    monkeypatch.setenv("DAMIA_CACHE__MAX_ENTRIES", "7")
    monkeypatch.setenv("DAMIA_RETRY__ENABLED", "true")
    monkeypatch.setenv("DAMIA_RETRY__MAX_ATTEMPTS", "2")
    config = DamiaSettings.from_env()
    assert config.damia_key is not None
    assert config.damia_key.get_secret_value() == "synthetic-shared"
    assert (
        config.cache.enabled
        and config.cache.ttl == 12
        and config.cache.max_entries == 7
    )
    assert config.retry.enabled and config.retry.max_attempts == 2
    assert "synthetic-shared" not in repr(config)


@pytest.mark.asyncio
async def test_cached_requests_are_bounded_by_lru() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"value": request.url.params["req"]})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True, ttl=10, max_entries=2)),
        transport=httpx.MockTransport(handle),
    ) as client:

        async def get(req: str) -> bool:
            response = await client.request(
                "GET",
                "/egr",
                service="fns",
                params=[("req", req)],
                allow_cache=True,
                cache_validator=lambda r: True,
            )
            return response.from_cache

        assert not await get("1")
        assert not await get("2")
        assert await get("1")
        assert not await get("3")
        assert not await get("2")
        assert calls == 4


@pytest.mark.asyncio
async def test_non_json_is_not_cached() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="ok")

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    ) as client:
        for _ in range(2):
            result = await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
            )
            assert not result.from_cache
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_is_disabled_by_default_even_when_operation_opts_in() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    async with HttpClient(settings(), transport=httpx.MockTransport(handle)) as client:
        for _ in range(2):
            response = await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
            )
            assert not response.from_cache
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_ttl_override_does_not_share_longer_lived_entries() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True, ttl=60)),
        transport=httpx.MockTransport(handle),
    ) as client:
        long = await client.request(
            "GET",
            "/egr",
            service="fns",
            allow_cache=True,
            cache_validator=lambda r: True,
        )
        short = await client.request(
            "GET",
            "/egr",
            service="fns",
            allow_cache=True,
            cache_validator=lambda r: True,
            cache_ttl=0.02,
        )
        assert not long.from_cache and not short.from_cache
        await asyncio.sleep(0.04)
        short_again = await client.request(
            "GET",
            "/egr",
            service="fns",
            allow_cache=True,
            cache_validator=lambda r: True,
            cache_ttl=0.02,
        )
        assert not short_again.from_cache
        assert calls == 3
        with pytest.raises(DamiaConfigurationError):
            await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
                cache_ttl=0,
            )


@pytest.mark.asyncio
async def test_cancelled_singleflight_leader_does_not_block_waiters() -> None:
    entered = asyncio.Event()
    never = asyncio.Event()
    calls = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await never.wait()
        return httpx.Response(200, json={"ok": True})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    ) as client:

        async def get() -> int:
            result = await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
            )
            return result.status_code

        leader = asyncio.create_task(get())
        await entered.wait()
        waiter = asyncio.create_task(get())
        await asyncio.sleep(0)
        leader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await leader
        assert await asyncio.wait_for(waiter, timeout=1) == 200
        assert calls == 2
        assert not client._flights


@pytest.mark.asyncio
async def test_cache_size_limit_skips_large_entries() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"large": "value"})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True, max_entry_bytes=1)),
        transport=httpx.MockTransport(handle),
    ) as client:
        for _ in range(2):
            await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
            )
    assert calls == 2


@pytest.mark.asyncio
async def test_retry_globally_disabled_even_if_operation_opts_in() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with HttpClient(settings(), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(DamiaHTTPError):
            await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert calls == 1


@pytest.mark.asyncio
async def test_asynchronous_zsk_polling_is_not_automatic_retry() -> None:
    async with HttpClient(
        settings(retry=RetrySettings(enabled=True)),
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    ) as client:
        with pytest.raises(DamiaConfigurationError):
            await client.request("GET", "/zsk", service="fns", allow_retry=True)


@pytest.mark.asyncio
async def test_unauthorized_status_is_not_retried() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    async with HttpClient(
        settings(retry=RetrySettings(enabled=True, max_attempts=3, initial_delay=0)),
        transport=httpx.MockTransport(handle),
    ) as client:
        with pytest.raises(DamiaHTTPError) as exc:
            await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert exc.value.status_code == 401
    assert calls == 1


@pytest.mark.asyncio
async def test_exhausted_retries_do_not_expose_httpx_request() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError(f"URL {request.url}", request=request)

    async with HttpClient(
        settings(retry=RetrySettings(enabled=True, max_attempts=2, initial_delay=0)),
        transport=httpx.MockTransport(handle),
    ) as client:
        with pytest.raises(DamiaConnectionError) as exc:
            await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert calls == 2
    assert "test-secret" not in "".join(traceback.format_exception(exc.value))
    assert exc.value.__context__ is None


@pytest.mark.asyncio
async def test_retry_total_deadline_and_cancellation() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200)

    policy = RetrySettings(enabled=True, max_attempts=3, max_elapsed=0.02)
    async with HttpClient(
        settings(retry=policy), transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(DamiaTimeoutError) as exc:
            await client.request("GET", "/egr", service="fns", allow_retry=True)
        assert exc.value.__context__ is None
        task = asyncio.create_task(
            client.request("GET", "/egr", service="fns", allow_retry=True)
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base",
    [
        "https://user:secret@example.com",
        "https://example.com/?key=secret",
        "https://example.com/#secret",
        "https://[invalid",
        "https://example.com:bad",
        "https://example.com/%2e%2e",
        "https://example.com/\nprivate",
    ],
)
async def test_invalid_base_address_never_leaks_its_contents(base: str) -> None:
    config = DamiaSettings(
        fns_key=SecretStr("test-key"), base_urls=BaseURLSettings(fns=base)
    )
    async with HttpClient(
        config, transport=httpx.MockTransport(lambda r: httpx.Response(200))
    ) as client:
        with pytest.raises(DamiaConfigurationError) as exc:
            await client.request("GET", "/egr", service="fns")
    assert base not in str(exc.value)
    assert exc.value.__context__ is None


@pytest.mark.asyncio
async def test_clear_during_request_prevents_late_cache_write() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return httpx.Response(200, json={"call": calls})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    ) as client:

        async def get() -> HttpResponse:
            return await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
            )

        task = asyncio.create_task(get())
        await entered.wait()
        await client.clear_cache()
        release.set()
        await task
        await get()
        await get()
        assert calls == 2
        assert not client._flights


@pytest.mark.asyncio
async def test_failed_delete_does_not_restore_old_or_delete_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"call": calls})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    ) as client:

        async def get() -> HttpResponse:
            return await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
            )

        await get()
        backend = client._cache._cache
        delete = backend.delete
        attempts: list[str] = []

        async def failing(key: str) -> int:
            attempts.append(key)
            raise ValueError("secret")

        monkeypatch.setattr(backend, "delete", failing)
        with pytest.raises(RuntimeError, match="очистить"):
            await client.clear_cache()
        await get()
        assert calls == 2
        monkeypatch.setattr(backend, "delete", delete)
        # Retry invalidates current entries too, but old and new physical keys differ.
        keys = set(client._cache._keys)
        assert keys.isdisjoint(attempts)
        await client.clear_cache()
        assert not client._cache._pending


@pytest.mark.asyncio
async def test_close_waiters_and_single_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    from damia_sdk import DamiaClientClosedError

    entered, release, closing, finish = (asyncio.Event() for _ in range(4))

    async def handle(request: httpx.Request) -> httpx.Response:
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    )
    original_close = client._cache.close

    async def slow_close() -> None:
        closing.set()
        await finish.wait()
        await original_close()

    monkeypatch.setattr(client._cache, "close", slow_close)

    async def get() -> HttpResponse:
        return await client.request(
            "GET",
            "/egr",
            service="fns",
            allow_cache=True,
            cache_validator=lambda r: True,
        )

    first = asyncio.create_task(get())
    await entered.wait()
    second = asyncio.create_task(get())
    await asyncio.sleep(0)
    close1 = asyncio.create_task(client.aclose())
    await closing.wait()
    close2 = asyncio.create_task(client.aclose())
    await asyncio.sleep(0)
    close1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close1
    release.set()
    await first
    with pytest.raises(DamiaClientClosedError):
        await second
    assert not client._cache._keys
    assert not client._flights
    finish.set()
    await close2
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime", "cached"),
    [
        ("application/json", True),
        ("APPLICATION/JSON; charset=utf-8", True),
        ("application/example+json", False),
        ("text/example+json", False),
        ("text/plain", False),
        ("application/octet-stream", False),
    ],
)
async def test_mime_cache_policy_and_data(mime: str, cached: bool) -> None:
    async with HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, content=b'{"ok":true}', headers={"Content-Type": mime}
            )
        ),
    ) as client:

        async def get(valid: bool) -> HttpResponse:
            return await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: valid,
            )

        response = await get(False)
        assert response.data == (
            {"ok": True}
            if "json" in mime.lower()
            else ('{"ok":true}' if mime.startswith("text/") else b'{"ok":true}')
        )
        assert not (await get(True)).from_cache
        assert (await get(True)).from_cache is cached


@pytest.mark.asyncio
async def test_mixed_validators_revalidate_shared_cache() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"n": calls})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    ) as client:

        async def get(n: int) -> HttpResponse:
            return await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: r.json() == {"n": n},
            )

        await get(1)
        assert (await get(1)).from_cache
        assert not (await get(2)).from_cache
        assert (await get(2)).from_cache
        assert calls == 2


@pytest.mark.asyncio
async def test_cleanup_attempts_all_and_retries_failed_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    for value in ("a", "b"):
        await client.request(
            "GET",
            "/egr",
            service="fns",
            params=[("req", value)],
            allow_cache=True,
            cache_validator=lambda r: True,
        )
    backend = client._cache._cache
    delete = backend.delete
    close = backend.close
    keys = list(client._cache._keys)
    attempted: list[str] = []
    closes = 0

    async def faulty(key: str) -> int:
        attempted.append(key)
        if key == keys[0]:
            raise ValueError("sensitive")
        result: int = await delete(key)
        return result

    async def counted_close() -> None:
        nonlocal closes
        closes += 1
        await close()

    monkeypatch.setattr(backend, "delete", faulty)
    monkeypatch.setattr(backend, "close", counted_close)
    with pytest.raises(RuntimeError, match="ресурсы") as error:
        await client.aclose()
    assert "sensitive" not in str(error.value)
    assert set(attempted) == set(keys)
    assert client._cache._pending == {keys[0]}
    assert closes == 1
    monkeypatch.setattr(backend, "delete", delete)
    await client.aclose()
    assert not client._cache._pending
    assert closes == 1


@pytest.mark.asyncio
async def test_transport_close_failure_is_retried_directly() -> None:
    class FailingCloseTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.close_calls = 0

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        async def aclose(self) -> None:
            self.close_calls += 1
            if self.close_calls == 1:
                raise RuntimeError("sensitive transport failure")

    transport = FailingCloseTransport()
    client = HttpClient(settings(), transport=transport)
    await client.request("GET", "/egr", service="fns")
    with pytest.raises(RuntimeError, match="ресурсы") as error:
        await client.aclose()
    assert "sensitive transport failure" not in str(error.value)
    assert client._http.is_closed
    assert transport.close_calls == 1
    await client.aclose()
    assert transport.close_calls == 2
    await client.aclose()
    assert transport.close_calls == 2


@pytest.mark.asyncio
async def test_cancelled_clear_keeps_keys_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    await client.request(
        "GET", "/egr", service="fns", allow_cache=True, cache_validator=lambda r: True
    )
    backend = client._cache._cache
    delete = backend.delete
    entered = asyncio.Event()

    async def blocked(key: str) -> int:
        entered.set()
        await asyncio.Event().wait()
        return 0

    monkeypatch.setattr(backend, "delete", blocked)
    task = asyncio.create_task(client.clear_cache())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client._cache._pending and not client._cache._keys
    monkeypatch.setattr(backend, "delete", delete)
    await client.aclose()
    assert not client._cache._pending


@pytest.mark.asyncio
async def test_backend_commit_cannot_write_after_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Callable

    entered, release, closing = (asyncio.Event() for _ in range(3))
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"call": calls})

    client = HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    )
    backend = client._cache._cache
    original_set = backend.set
    original_close = client._cache.close
    writes: list[bool] = []

    class ObservedValues(dict[str, HttpResponse]):
        def __setitem__(self, key: str, value: HttpResponse) -> None:
            writes.append(client._closed)
            super().__setitem__(key, value)

    backend._values = ObservedValues()

    async def blocked_set(
        key: str,
        value: HttpResponse,
        *,
        ttl: float | None,
        permitted: Callable[[], bool] | None,
    ) -> bool:
        entered.set()
        await release.wait()
        return await original_set(key, value, ttl=ttl, permitted=permitted)

    async def observed_close() -> None:
        assert client._closed
        closing.set()
        await original_close()

    async def get(req: str) -> HttpResponse:
        return await client.request(
            "GET",
            "/egr",
            service="fns",
            params=[("req", req)],
            allow_cache=True,
            cache_validator=lambda r: True,
        )

    tasks: list[asyncio.Task[object]] = []
    try:
        await get("1")
        assert (await get("1")).from_cache
        assert calls == 1 and writes == [False]
        monkeypatch.setattr(backend, "set", blocked_set)
        monkeypatch.setattr(client._cache, "close", observed_close)
        request = asyncio.create_task(get("2"))
        tasks.append(request)
        await asyncio.wait_for(entered.wait(), 1)
        close = asyncio.create_task(client.aclose())
        tasks.append(close)
        await asyncio.wait_for(closing.wait(), 1)
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 1)
        assert writes == [False]
        assert not backend._values and not client._cache._pending
        assert not client._flights
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.aclose()


@pytest.mark.asyncio
async def test_parallel_close_waiters_share_failed_cleanup_and_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release, joined = (asyncio.Event() for _ in range(3))
    client = HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    await client.request(
        "GET", "/egr", service="fns", allow_cache=True, cache_validator=lambda r: True
    )
    backend = client._cache._cache
    key = next(iter(client._cache._keys))
    delete, backend_close, http_close = (
        backend.delete,
        backend.close,
        client._http.aclose,
    )
    shield = asyncio.shield
    deletes = backend_closes = http_closes = shields = 0

    async def failing_delete(key: str) -> int:
        nonlocal deletes
        deletes += 1
        entered.set()
        await release.wait()
        raise ValueError("delete failed")

    async def counted_backend_close() -> None:
        nonlocal backend_closes
        backend_closes += 1
        await backend_close()

    async def counted_http_close() -> None:
        nonlocal http_closes
        http_closes += 1
        await http_close()

    def observed_shield(task: asyncio.Task[None]) -> asyncio.Future[None]:
        nonlocal shields
        assert task is client._close_task
        shields += 1
        if shields == 2:
            joined.set()
        return shield(task)

    monkeypatch.setattr(backend, "delete", failing_delete)
    monkeypatch.setattr(backend, "close", counted_backend_close)
    monkeypatch.setattr(client._http, "aclose", counted_http_close)
    monkeypatch.setattr(asyncio, "shield", observed_shield)
    tasks: list[asyncio.Task[None]] = []
    try:
        tasks.append(asyncio.create_task(client.aclose()))
        await asyncio.wait_for(entered.wait(), 1)
        tasks.append(asyncio.create_task(client.aclose()))
        await asyncio.wait_for(joined.wait(), 1)
        release.set()
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), 1
        )
        assert all(isinstance(result, RuntimeError) for result in results)
        assert (deletes, backend_closes, http_closes) == (1, 1, 1)
        assert client._cache._pending == {key}
        monkeypatch.setattr(backend, "delete", delete)
        await asyncio.wait_for(client.aclose(), 1)
        assert not client._cache._pending
        assert (backend_closes, http_closes) == (1, 1)
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        monkeypatch.setattr(backend, "delete", delete)
        await client.aclose()


@pytest.mark.asyncio
async def test_cancelled_backend_set_keeps_written_key_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Callable

    client = HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    backend = client._cache._cache
    original_set = backend.set
    entered = asyncio.Event()

    async def interrupted_set(
        key: str,
        value: HttpResponse,
        *,
        ttl: float | None,
        permitted: Callable[[], bool] | None,
    ) -> bool:
        committed = await original_set(key, value, ttl=ttl, permitted=permitted)
        entered.set()
        await asyncio.Event().wait()
        return committed

    monkeypatch.setattr(backend, "set", interrupted_set)
    task = asyncio.create_task(
        client.request(
            "GET",
            "/egr",
            service="fns",
            allow_cache=True,
            cache_validator=lambda r: True,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert set(backend._values) == client._cache._pending
        assert client._cache._pending and not client._cache._keys
        await asyncio.wait_for(client.aclose(), 1)
        assert not backend._values and not client._cache._pending
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.aclose()


@pytest.mark.asyncio
async def test_rejected_commit_preserves_pending_eviction_for_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import Callable

    entered, release, closing = (asyncio.Event() for _ in range(3))
    client = HttpClient(
        settings(cache=CacheSettings(enabled=True, max_entries=1)),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    backend = client._cache._cache
    original_delete, original_set = backend.delete, backend.set
    original_close = client._cache.close

    async def get(req: str) -> HttpResponse:
        return await client.request(
            "GET",
            "/egr",
            service="fns",
            params=[("req", req)],
            allow_cache=True,
            cache_validator=lambda r: True,
        )

    async def failing_delete(key: str) -> int:
        raise ValueError("eviction failed")

    async def blocked_set(
        key: str,
        value: HttpResponse,
        *,
        ttl: float | None,
        permitted: Callable[[], bool] | None,
    ) -> bool:
        entered.set()
        await release.wait()
        committed = await original_set(key, value, ttl=ttl, permitted=permitted)
        assert not committed
        return committed

    async def observed_close() -> None:
        closing.set()
        await original_close()

    tasks: list[asyncio.Task[object]] = []
    try:
        await get("a")
        key = next(iter(client._cache._keys))
        monkeypatch.setattr(backend, "delete", failing_delete)
        await get("b")
        assert key in backend._values and client._cache._pending == {key}
        monkeypatch.setattr(backend, "delete", original_delete)
        monkeypatch.setattr(backend, "set", blocked_set)
        monkeypatch.setattr(client._cache, "close", observed_close)
        tasks.append(asyncio.create_task(get("a")))
        await asyncio.wait_for(entered.wait(), 1)
        tasks.append(asyncio.create_task(client.aclose()))
        await asyncio.wait_for(closing.wait(), 1)
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 1)
        assert key not in backend._values
        assert not client._cache._pending
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        monkeypatch.setattr(backend, "delete", original_delete)
        await client.aclose()


@pytest.mark.asyncio
async def test_retry_after_overflowing_integer_prevents_retry() -> None:
    from damia_sdk import DamiaRateLimitError

    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "9" * 400})

    async with HttpClient(
        settings(retry=RetrySettings(enabled=True, max_attempts=2, initial_delay=0)),
        transport=httpx.MockTransport(handle),
    ) as client:
        with pytest.raises(DamiaRateLimitError) as exc:
            await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert calls == 1
    assert exc.value.retry_after == float("inf")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header", "expected", "calls"),
    [
        ("invalid", None, 2),
        ("inf", None, 2),
        ("nan", None, 2),
        ("1e999", None, 2),
        ("0", 0.0, 2),
        ("-2", 0.0, 2),
        ("1.5", 1.5, 2),
        ("2", 2.0, 2),
        ("3", 3.0, 1),
    ],
)
async def test_retry_after_numeric_and_invalid(
    monkeypatch: pytest.MonkeyPatch, header: str, expected: float | None, calls: int
) -> None:
    import damia_sdk.transport.http as http_module

    sleeps: list[float] = []
    original = AsyncRetrying

    async def sleep(delay: float) -> None:
        sleeps.append(float(delay))

    monkeypatch.setattr(
        http_module, "AsyncRetrying", lambda **kw: original(sleep=sleep, **kw)
    )
    monkeypatch.setattr(
        http_module, "wait_random_exponential", lambda **kw: lambda state: 0.25
    )
    count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(429, headers={"Retry-After": header})

    policy = RetrySettings(enabled=True, max_attempts=2, initial_delay=0, max_delay=2)
    async with HttpClient(
        settings(retry=policy), transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(DamiaHTTPError) as exc:
            await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert count == calls
    assert exc.value.retry_after == expected
    assert sleeps == ([max(0.25, expected or 0)] if calls == 2 else [])


@pytest.mark.asyncio
@pytest.mark.parametrize(("offset", "calls"), [(2, 2), (3, 1), (-1, 2)])
async def test_retry_after_http_date(
    monkeypatch: pytest.MonkeyPatch, offset: int, calls: int
) -> None:
    from datetime import UTC, datetime, timedelta, tzinfo
    from email.utils import format_datetime
    from typing import Self

    import damia_sdk.transport.http as http_module

    now = datetime(2025, 1, 1, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2025, 1, 1, tzinfo=UTC)

    sleeps: list[float] = []
    original = AsyncRetrying

    async def sleep(delay: float) -> None:
        sleeps.append(float(delay))

    monkeypatch.setattr(http_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        http_module, "AsyncRetrying", lambda **kw: original(sleep=sleep, **kw)
    )
    monkeypatch.setattr(
        http_module, "wait_random_exponential", lambda **kw: lambda state: 0.25
    )
    count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(
            429,
            headers={
                "Retry-After": format_datetime(
                    now + timedelta(seconds=offset), usegmt=True
                )
            },
        )

    policy = RetrySettings(enabled=True, max_attempts=2, initial_delay=0, max_delay=2)
    async with HttpClient(
        settings(retry=policy), transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(DamiaHTTPError) as exc:
            await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert count == calls
    assert exc.value.retry_after == max(0, offset)
    assert sleeps == ([max(0.25, offset)] if calls == 2 else [])


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 400, 401, 403, 404, 501])
@pytest.mark.parametrize("eventual_success", [False, True])
async def test_retry_http_status_policy(status: int, eventual_success: bool) -> None:
    from damia_sdk import DamiaRateLimitError

    retryable = status in (429, 500, 502, 503, 504)
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200 if eventual_success and calls == 2 else status)

    policy = RetrySettings(enabled=True, max_attempts=2, initial_delay=0)
    async with HttpClient(
        settings(retry=policy), transport=httpx.MockTransport(handle)
    ) as client:
        if retryable and eventual_success:
            assert (
                await client.request("GET", "/egr", service="fns", allow_retry=True)
            ).status_code == 200
        else:
            error = DamiaRateLimitError if status == 429 else DamiaHTTPError
            with pytest.raises(error) as exc:
                await client.request("GET", "/egr", service="fns", allow_retry=True)
            assert type(exc.value) is error
            assert exc.value.status_code == status
    assert calls == (2 if retryable else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
@pytest.mark.parametrize("eventual_success", [False, True])
async def test_retry_network_failures(
    failure: type[httpx.RequestError], eventual_success: bool
) -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if eventual_success and calls == 2:
            return httpx.Response(200)
        raise failure("failure", request=request)

    policy = RetrySettings(enabled=True, max_attempts=2, initial_delay=0)
    async with HttpClient(
        settings(retry=policy), transport=httpx.MockTransport(handle)
    ) as client:
        if eventual_success:
            assert (
                await client.request("GET", "/egr", service="fns", allow_retry=True)
            ).status_code == 200
        else:
            error = (
                DamiaTimeoutError
                if failure is httpx.ReadTimeout
                else DamiaConnectionError
            )
            with pytest.raises(error) as exc:
                await client.request("GET", "/egr", service="fns", allow_retry=True)
            assert type(exc.value) is error
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [True, False])
async def test_retry_backoff_cancellation_and_deadline(
    monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    import damia_sdk.transport.http as http_module

    entered = asyncio.Event()
    original = AsyncRetrying
    calls = 0

    async def sleep(delay: float) -> None:
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        http_module, "AsyncRetrying", lambda **kw: original(sleep=sleep, **kw)
    )

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    policy = RetrySettings(
        enabled=True, max_attempts=2, initial_delay=0, max_elapsed=0.1
    )
    async with HttpClient(
        settings(retry=policy), transport=httpx.MockTransport(handle)
    ) as client:
        task = asyncio.create_task(
            client.request("GET", "/egr", service="fns", allow_retry=True)
        )
        try:
            await asyncio.wait_for(entered.wait(), 1)
            if cancel:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else DamiaTimeoutError):
                await asyncio.wait_for(task, 1)
            assert calls == 1
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cache_expired_mru_does_not_evict_live_lru() -> None:
    from damia_sdk.transport.cache import ResponseCache

    cache = ResponseCache(CacheSettings(enabled=True, max_entries=2))
    response = HttpResponse(200, "application/json", b"{}")
    try:
        await cache.set("a", response, ttl=60)
        await cache.set("b", response, ttl=0.01)
        await asyncio.sleep(0.03)
        await cache.set("c", response, ttl=60)
        assert await cache.get("a") is not None
        assert await cache.get("b") is None
        assert await cache.get("c") is not None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_cache_live_lru_replacement_and_expiry_cleanup() -> None:
    from damia_sdk.transport.cache import ResponseCache

    cache = ResponseCache(CacheSettings(enabled=True, max_entries=2))
    first = HttpResponse(200, "application/json", b"first")
    replacement = HttpResponse(200, "application/json", b"replacement")
    try:
        await cache.set("a", first, ttl=60)
        await cache.set("b", first, ttl=60)
        await cache.set("a", replacement, ttl=0.01)
        assert (await cache.get("a")) == HttpResponse(
            200, "application/json", b"replacement", from_cache=True
        )
        await cache.set("c", first, ttl=60)
        assert await cache.get("b") is None
        assert await cache.get("a") is not None
        await asyncio.sleep(0.03)
        assert await cache.get("a") is None
        assert len(cache._keys) == 1
    finally:
        await cache.close()
    assert not cache._keys and not cache._pending and not cache._cache._values


@pytest.mark.asyncio
async def test_cache_scan_error_does_not_evict_live_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from damia_sdk.transport.cache import ResponseCache

    cache = ResponseCache(CacheSettings(enabled=True, max_entries=2))
    response = HttpResponse(200, "application/json", b"{}")
    backend = cache._cache
    original_get = backend.get
    try:
        await cache.set("a", response, ttl=60)
        await cache.set("b", response, ttl=60)

        async def failing_get(key: str) -> HttpResponse | None:
            if key.endswith(":b"):
                raise ValueError("backend failure")
            return await original_get(key)

        monkeypatch.setattr(backend, "get", failing_get)
        await cache.set("c", response, ttl=60)
        monkeypatch.setattr(backend, "get", original_get)
        assert await cache.get("a") is not None
        assert await cache.get("b") is not None
        assert await cache.get("c") is None
    finally:
        await cache.close()


@pytest.mark.asyncio
async def test_clear_with_queued_singleflight_waiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release, queued = (asyncio.Event() for _ in range(3))
    calls = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return httpx.Response(200, json={"call": calls})

    async with HttpClient(
        settings(cache=CacheSettings(enabled=True)),
        transport=httpx.MockTransport(handle),
    ) as client:

        async def get() -> HttpResponse:
            return await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: True,
            )

        leader = asyncio.create_task(get())
        waiter: asyncio.Task[HttpResponse] | None = None
        try:
            await asyncio.wait_for(entered.wait(), 1)
            flight = next(iter(client._flights.values()))
            acquire = flight.lock.acquire

            async def observed_acquire() -> bool:
                queued.set()
                return await acquire()

            monkeypatch.setattr(flight.lock, "acquire", observed_acquire)
            waiter = asyncio.create_task(get())
            await asyncio.wait_for(queued.wait(), 1)
            assert flight.users == 2
            await client.clear_cache()
            release.set()
            leader_result, waiter_result = await asyncio.wait_for(
                asyncio.gather(leader, waiter), 1
            )
            assert leader_result.json() == {"call": 1}
            assert waiter_result.json() == {"call": 2}
            cached = await get()
            assert cached.from_cache and cached.json() == {"call": 2}
            assert calls == 2 and not client._flights
        finally:
            release.set()
            leader.cancel()
            if waiter is not None:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
            await asyncio.gather(leader, return_exceptions=True)


@pytest.mark.asyncio
async def test_httpx_info_logs_hide_query_without_affecting_other_clients(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    seen: list[tuple[str, str]] = []
    closed = False

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            seen.append((request.url.params["key"], request.url.params["person"]))
            await asyncio.sleep(0)
            if request.url.params["person"] == "synthetic-person-error":
                raise httpx.ConnectError("synthetic failure", request=request)
            return httpx.Response(200, text="ok", request=request)

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    caplog.set_level(logging.INFO, logger="httpx")
    async with HttpClient(settings(), transport=Transport()) as client:
        await asyncio.gather(
            *(
                client.request(
                    "GET", "/egr", service="fns", params=[("person", person)]
                )
                for person in ("synthetic-person-one", "synthetic-person-two")
            )
        )
        with pytest.raises(DamiaConnectionError):
            await client.request(
                "GET",
                "/egr",
                service="fns",
                params=[("person", "synthetic-person-error")],
            )
    assert closed
    assert set(seen) == {
        ("test-secret", "synthetic-person-one"),
        ("test-secret", "synthetic-person-two"),
        ("test-secret", "synthetic-person-error"),
    }
    records = [record for record in caplog.records if record.name == "httpx"]
    assert len(records) == 2
    for record in records:
        assert "test-secret" not in record.getMessage() + repr(record.args)
        assert "synthetic-person" not in record.getMessage() + repr(record.args)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200))
    ) as other:
        await other.get("https://example.test/", params={"ordinary": "visible"})
    assert "ordinary=visible" in caplog.records[-1].getMessage()
