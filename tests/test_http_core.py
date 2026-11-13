"""Изолированные тесты HTTP-транспорта без запросов к DaMIA."""

import asyncio
import traceback
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from damia_sdk import (
    BaseURLSettings,
    CacheSettings,
    DamiaClient,
    DamiaClientClosedError,
    DamiaConfigurationError,
    DamiaConnectionError,
    DamiaHTTPError,
    DamiaRateLimitError,
    DamiaResponseError,
    DamiaSettings,
    DamiaTimeoutError,
    RetrySettings,
)
from damia_sdk.transport import HttpClient, HttpResponse
from damia_sdk.transport.http import ServiceName


def configured(
    *,
    retry: RetrySettings | None = None,
    cache: CacheSettings | None = None,
) -> DamiaSettings:
    return DamiaSettings(
        fns_key=SecretStr("synthetic-fns-key"),
        banks_key=SecretStr("synthetic-banks-key"),
        damia_key=SecretStr("synthetic-shared-key"),
        scoring_key=SecretStr("synthetic-scoring-key"),
        base_urls=BaseURLSettings(fns="http://127.0.0.1:4010"),
        retry=retry or RetrySettings(),
        cache=cache or CacheSettings(),
    )


def transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_request_uses_settings_and_preserves_repeated_query_params() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"value": "ok"})

    async with HttpClient(configured(), transport=transport(handle)) as client:
        result = await client.request(
            "GET",
            "/multinfo",
            service="fns",
            params=[("req[]", "001"), ("req[]", "002")],
        )
    assert result.status_code == 200
    assert result.json() == {"value": "ok"}
    assert not result.from_cache
    assert str(seen[0].url.copy_with(query=None)) == "http://127.0.0.1:4010/multinfo"
    assert seen[0].url.params.get_list("req[]") == ["001", "002"]
    assert seen[0].url.params["key"] == "synthetic-fns-key"
    assert "synthetic-fns-key" not in repr(result)


@pytest.mark.asyncio
async def test_credentials_select_service_override_then_shared_key() -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["key"])
        return httpx.Response(200, json={})

    async with HttpClient(configured(), transport=transport(handle)) as client:
        await client.request("GET", "/info", service="scoring")
        await client.request("GET", "/balance", service="rosstat")
        await client.request("GET", "/api/stat", service="banks")
    assert seen == [
        "synthetic-scoring-key",
        "synthetic-shared-key",
        "synthetic-banks-key",
    ]


@pytest.mark.asyncio
async def test_blank_service_override_never_uses_shared_credentials() -> None:
    settings = DamiaSettings(damia_key=SecretStr("shared"), scoring_key=SecretStr(""))
    async with HttpClient(
        settings, transport=transport(lambda req: httpx.Response(200))
    ) as client:
        with pytest.raises(DamiaConfigurationError, match="ключ"):
            await client.request("GET", "/info", service="scoring")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [301, 400, 401, 403, 500])
async def test_http_status_errors_are_safe_and_redirects_are_not_followed(
    status: int,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status, text="sensitive-body", headers={"Location": "https://other.invalid"}
        )

    sensitive_value = "private-value"
    async with HttpClient(configured(), transport=transport(handle)) as client:
        with pytest.raises(DamiaHTTPError) as exc:
            await client.request(
                "GET", "/egr", service="fns", params=[("req", sensitive_value)]
            )
    assert exc.value.status_code == status
    assert len(requests) == 1
    rendered = "".join(traceback.format_exception(exc.value))
    assert "synthetic-fns-key" not in rendered
    assert "private-value" not in rendered
    assert "sensitive-body" not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_network_errors_do_not_chain_secret_bearing_httpx_exceptions(
    error_type: type[httpx.RequestError],
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error_type(f"leaked {request.url}", request=request)

    sensitive_value = "private-value"
    async with HttpClient(configured(), transport=transport(handle)) as client:
        with pytest.raises(DamiaConnectionError) as exc:
            await client.request(
                "GET", "/egr", service="fns", params=[("req", sensitive_value)]
            )
    assert exc.value.__context__ is None
    assert exc.value.__cause__ is None
    assert "synthetic-fns-key" not in "".join(traceback.format_exception(exc.value))
    assert "private-value" not in "".join(traceback.format_exception(exc.value))
    if error_type is httpx.ReadTimeout:
        assert isinstance(exc.value, DamiaTimeoutError)


@pytest.mark.asyncio
async def test_retry_requires_both_settings_and_operation_opt_in() -> None:
    attempts = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    policy = RetrySettings(enabled=True, max_attempts=3, initial_delay=0, max_elapsed=2)
    async with HttpClient(
        configured(retry=policy), transport=transport(handle)
    ) as client:
        with pytest.raises(DamiaHTTPError):
            await client.request("GET", "/egr", service="fns")
        assert attempts == 1
        attempts = 0
        response = await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert attempts == 3
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_retry_does_not_retry_auth_or_excessive_retry_after() -> None:
    attempts = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "60"})

    policy = RetrySettings(enabled=True, max_attempts=3, initial_delay=0, max_delay=1)
    async with HttpClient(
        configured(retry=policy), transport=transport(handle)
    ) as client:
        with pytest.raises(DamiaRateLimitError) as exc:
            await client.request("GET", "/egr", service="fns", allow_retry=True)
    assert attempts == 1
    assert exc.value.retry_after == 60


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "path"),
    [("fns", "/mon"), ("procurement", "/zmon"), ("arbitration", "/arb/delopro")],
)
async def test_mutating_gets_cannot_be_retried_or_cached(
    service: ServiceName, path: str
) -> None:
    attempts = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={})

    policy = RetrySettings(enabled=True)
    cache = CacheSettings(enabled=True)
    async with HttpClient(
        configured(retry=policy, cache=cache), transport=transport(handle)
    ) as client:
        with pytest.raises(DamiaConfigurationError):
            await client.request("GET", path, service=service, allow_retry=True)
        with pytest.raises(DamiaConfigurationError):
            await client.request(
                "GET",
                path,
                service=service,
                allow_cache=True,
                cache_validator=lambda r: True,
            )
        await client.request("GET", path, service=service)
    assert attempts == 1


@pytest.mark.asyncio
async def test_cache_expiry_validation_singleflight_and_no_plaintext_keys() -> None:
    attempts = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"ok": True})

    cache = CacheSettings(enabled=True, ttl=0.1, max_entries=2)
    async with HttpClient(
        configured(cache=cache), transport=httpx.MockTransport(handle)
    ) as client:

        async def call() -> HttpResponse:
            return await client.request(
                "GET",
                "/egr",
                service="fns",
                params=[("req", "private-value")],
                allow_cache=True,
                cache_validator=lambda r: r.json() == {"ok": True},
            )

        first, second, third = await asyncio.gather(call(), call(), call())
        assert attempts == 1
        assert [first.from_cache, second.from_cache, third.from_cache] == [
            False,
            True,
            True,
        ]
        assert all(
            "private-value" not in key and "synthetic-fns-key" not in key
            for key in client._cache._keys
        )
        await asyncio.sleep(0.12)
        assert not (await call()).from_cache
        assert attempts == 2
        await client.clear_cache()
        assert not (await call()).from_cache
        assert attempts == 3


@pytest.mark.asyncio
async def test_cache_requires_validation_and_rejects_sensitive_or_file_paths() -> None:
    async with HttpClient(
        configured(cache=CacheSettings(enabled=True)),
        transport=transport(lambda r: httpx.Response(200)),
    ) as client:
        with pytest.raises(DamiaConfigurationError, match="проверка"):
            await client.request("GET", "/egr", service="fns", allow_cache=True)
        paths: list[tuple[ServiceName, str]] = [
            ("fns", "/innfl"),
            ("fns", "/vyp"),
            ("fssp", "/ispfl"),
        ]
        for service, path in paths:
            with pytest.raises(DamiaConfigurationError):
                await client.request(
                    "GET",
                    path,
                    service=service,
                    allow_cache=True,
                    cache_validator=lambda r: True,
                )


@pytest.mark.asyncio
async def test_rejected_cache_response_is_not_stored() -> None:
    attempts = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={"error": "synthetic-error"})

    async with HttpClient(
        configured(cache=CacheSettings(enabled=True)), transport=transport(handle)
    ) as client:
        for _ in range(2):
            response = await client.request(
                "GET",
                "/egr",
                service="fns",
                allow_cache=True,
                cache_validator=lambda r: r.json() == {"ok": True},
            )
            assert not response.from_cache
    assert attempts == 2


@pytest.mark.asyncio
async def test_configuration_rejects_unsafe_urls_keys_and_unsupported_method() -> None:
    async with HttpClient(
        configured(), transport=transport(lambda r: httpx.Response(200))
    ) as client:
        for path in (
            "https://attacker.invalid/x",
            "/egr?key=secret",
            "//evil/x",
            "/../egr",
        ):
            with pytest.raises(DamiaConfigurationError):
                await client.request("GET", path, service="fns")
        with pytest.raises(DamiaConfigurationError):
            await client.request(
                "GET", "/egr", service="fns", params=[("KEY", "secret")]
            )
        with pytest.raises(DamiaConfigurationError):
            await client.request("POST", "/egr", service="fns")
    bad = DamiaSettings(
        fns_key=SecretStr("secret"), base_urls=BaseURLSettings(fns="http://example.com")
    )
    async with HttpClient(
        bad, transport=transport(lambda r: httpx.Response(200))
    ) as client:
        with pytest.raises(DamiaConfigurationError):
            await client.request("GET", "/egr", service="fns")


@pytest.mark.parametrize(
    ("content_type", "body", "expected"),
    [
        ("application/json; charset=utf-8", b'{"ok": true}', {"ok": True}),
        ("application/problem+json", b"[1, 2]", [1, 2]),
        ("text/plain; charset=utf-8", "текст".encode(), "текст"),
        ("application/pdf", b"%PDF", b"%PDF"),
        (None, b"binary", b"binary"),
    ],
)
def test_response_data_uses_content_type(
    content_type: str | None, body: bytes, expected: object
) -> None:
    response = HttpResponse(200, content_type, body)
    assert response.data == expected
    assert response.body == body


def test_invalid_json_error_does_not_reveal_response() -> None:
    response = HttpResponse(200, "application/json", b"sensitive-invalid-json")
    with pytest.raises(DamiaResponseError) as exc:
        response.json()
    assert exc.value.__context__ is None
    assert "sensitive-invalid-json" not in "".join(
        traceback.format_exception(exc.value)
    )
    with pytest.raises(DamiaResponseError):
        _ = response.data


@pytest.mark.asyncio
async def test_client_closes_transport_and_cannot_be_reused() -> None:
    client = DamiaClient(
        settings=configured(), http_transport=transport(lambda req: httpx.Response(200))
    )
    async with client:
        await client._transport.request("GET", "/egr", service="fns")
    await client.aclose()
    with pytest.raises(DamiaClientClosedError):
        await client._transport.request("GET", "/egr", service="fns")
