"""Граничные сценарии повторов, кеширования и безопасного закрытия."""

import asyncio
import traceback

import httpx
import pytest
from pydantic import SecretStr

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
from damia_sdk.transport import HttpClient


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
