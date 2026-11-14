"""Characterization с синтетическими данными; MockTransport без сети."""

import traceback
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from damia_sdk import (
    BaseURLSettings,
    CacheSettings,
    DamiaConfigurationError,
    DamiaConnectionError,
    DamiaHTTPError,
    DamiaRateLimitError,
    DamiaSettings,
    DamiaTimeoutError,
    RetrySettings,
)
from damia_sdk.exceptions import DamiaResponseError
from damia_sdk.services.fns import FNSService
from damia_sdk.transport import HttpClient, HttpResponse

URL_MARKER = "synthetic-url"


def config(*, cache: bool = False, retry: bool = False) -> DamiaSettings:
    return DamiaSettings(
        fns_key=SecretStr("synthetic-key"),
        base_urls=BaseURLSettings(fns="https://example.invalid"),
        cache=CacheSettings(enabled=cache),
        retry=RetrySettings(enabled=retry, max_attempts=2, initial_delay=0),
    )


@pytest.mark.parametrize("status", [200, 201, 204, 299])
@pytest.mark.parametrize("body", [b"", b'{"ok":true}'])
@pytest.mark.asyncio
async def test_2xx_returns_response_and_json_is_lazy(status: int, body: bytes) -> None:
    async with HttpClient(
        config(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, content=body, headers={"Content-Type": "application/json"}
            )
        ),
    ) as client:
        response = await client.request("GET", "/egr", service="fns")
    assert response.status_code == status and response.body == body
    if body:
        assert response.data == {"ok": True}
    else:
        with pytest.raises(DamiaResponseError):
            _ = response.data


@pytest.mark.parametrize("body, expected", [(b"[]", []), (b"42", 42), (b"null", None)])
def test_json_explicitly_ignores_mime(body: bytes, expected: object) -> None:
    response = HttpResponse(200, "application/octet-stream", body)
    assert response.data == body and response.json() == expected


def test_text_replacement_and_repr_header_exposure() -> None:
    response = HttpResponse(
        200, "text/plain; marker=synthetic-header", b"synthetic-body\xff"
    )
    assert response.data == "synthetic-body\ufffd"
    assert "synthetic-body" not in repr(response)
    assert "synthetic-header" in repr(response)


def test_json_external_exception_context_is_caller_owned() -> None:
    try:
        raise ValueError("synthetic-external")
    except ValueError as outer:
        with pytest.raises(DamiaResponseError) as caught:
            HttpResponse(200, "application/json", b"synthetic-json-secret{").json()
        assert caught.value.__context__ is outer
        assert "synthetic-json-secret" not in str(caught.value) + repr(caught.value)
        assert caught.value.__cause__ is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [300, 400, 429, 500, 599])
async def test_http_errors_do_not_retain_synthetic_secrets(status: int) -> None:
    async with HttpClient(
        config(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status,
                content=b"synthetic-body",
                headers={"X-Request-ID": "synthetic-header", "Retry-After": "-2"},
            )
        ),
    ) as client:
        with pytest.raises(DamiaHTTPError) as caught:
            await client.request(
                "GET", "/egr", service="fns", params=[("req", URL_MARKER)]
            )
    error = caught.value
    assert type(error) is (DamiaRateLimitError if status == 429 else DamiaHTTPError)
    assert error.status_code == status and error.retry_after == 0
    assert error.__cause__ is None and error.__context__ is None
    assert not any(
        hasattr(error, name) for name in ("request", "response", "body", "url")
    )
    exposed = (
        str(error)
        + repr(error)
        + repr(vars(error))
        + "".join(traceback.format_exception(error))
    )
    assert all(
        secret not in exposed
        for secret in (
            "synthetic-body",
            "synthetic-header",
            "synthetic-url",
            "synthetic-key",
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure, expected",
    [
        (httpx.ReadTimeout, DamiaTimeoutError),
        (httpx.ConnectError, DamiaConnectionError),
    ],
)
async def test_network_errors_do_not_bind_httpx_exception(
    failure: type[httpx.RequestError], expected: type[Exception]
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise failure("synthetic-httpx " + str(request.url), request=request)

    async with HttpClient(config(), transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(expected) as caught:
            await client.request(
                "GET", "/egr", service="fns", params=[("req", URL_MARKER)]
            )
    error = caught.value
    assert error.__context__ is None and error.__cause__ is None
    assert not any(hasattr(error, name) for name in ("request", "response"))
    exposed = (
        str(error)
        + repr(error)
        + repr(vars(error))
        + "".join(traceback.format_exception(error))
    )
    assert all(
        secret not in exposed
        for secret in ("synthetic-httpx", "synthetic-url", "synthetic-key")
    )


@pytest.mark.asyncio
async def test_transport_external_exception_context_is_caller_owned() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic-httpx", request=request)

    async with HttpClient(config(), transport=httpx.MockTransport(handle)) as client:
        try:
            raise ValueError("synthetic-external")
        except ValueError as outer:
            with pytest.raises(DamiaConnectionError) as caught:
                await client.request("GET", "/egr", service="fns")
            assert caught.value.__context__ is outer
            assert caught.value.__cause__ is None
            assert "synthetic-httpx" not in str(caught.value) + repr(caught.value)


@pytest.mark.asyncio
async def test_json_failure_does_not_retry() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, content=b"bad", headers={"Content-Type": "application/json"}
        )

    async with HttpClient(
        config(retry=True), transport=httpx.MockTransport(handle)
    ) as client:
        response = await client.request("GET", "/egr", service="fns", allow_retry=True)
        with pytest.raises(DamiaResponseError):
            response.json()
    assert calls == 1


@pytest.mark.asyncio
async def test_cache_requires_validator_and_never_stores_http_errors() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={"synthetic": True})

    async with HttpClient(
        config(cache=True), transport=httpx.MockTransport(handle)
    ) as client:
        with pytest.raises(DamiaConfigurationError):
            await client.request("GET", "/egr", service="fns", allow_cache=True)
        for _ in range(2):
            with pytest.raises(DamiaHTTPError):
                await client.request(
                    "GET",
                    "/egr",
                    service="fns",
                    allow_cache=True,
                    cache_validator=lambda r: True,
                )
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["egr", "nalogbi_file"])
@pytest.mark.parametrize(
    "mime,body,expected",
    [
        ("application/json", b'{"synthetic":true}', {"synthetic": True}),
        ("application/octet-stream", b"\x00\xff", b"\x00\xff"),
        ("invalid", b'{"synthetic":true}', b'{"synthetic":true}'),
    ],
)
async def test_fns_services_pass_synthetic_responses(
    method: str, mime: str, body: bytes, expected: object
) -> None:
    async with HttpClient(
        config(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=body, headers={"Content-Type": mime}
            )
        ),
    ) as client:
        response = await getattr(FNSService(client), method)()
    assert response.body == body and response.data == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["egr", "nalogbi_file"])
async def test_fns_services_propagate_http_error(method: str) -> None:
    async with HttpClient(
        config(), transport=httpx.MockTransport(lambda request: httpx.Response(403))
    ) as client:
        with pytest.raises(DamiaHTTPError) as caught:
            await getattr(FNSService(client), method)()
    assert caught.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "service,method,path",
    [
        ("fns", "egr", "/egr"),
        ("rosstat", "balance", "/balance"),
        ("procurement", "zmon", "/zmon"),
        ("spk", "report", "/report"),
        ("spk", "proverki", "/proverki"),
        *(
            ("fns", name, "/" + name)
            for name in ("nalogbi_file", "vyp", "mspinfo_file", "bo_file")
        ),
    ],
)
@pytest.mark.parametrize(
    "status,mime,body,expected",
    [
        (200, "application/json", b'{"ok":true}', {"ok": True}),
        (200, "application/json", b"synthetic-body{", None),
        (200, "text/plain", b"text", "text"),
        (200, "application/octet-stream", b"\x00\xff", b"\x00\xff"),
        (403, "text/plain", b"synthetic-body", None),
    ],
)
async def test_representative_service_responses(
    service: str,
    method: str,
    path: str,
    status: int,
    mime: str,
    body: bytes,
    expected: Any,
) -> None:
    from damia_sdk import DamiaClient

    requests: list[httpx.Request] = []
    secret = SecretStr("synthetic-key")
    settings = DamiaSettings(
        fns_key=secret,
        damia_key=secret,
        banks_key=secret,
        scoring_key=secret,
        base_urls=BaseURLSettings.model_validate(
            {
                name: "https://example.invalid"
                for name in ("fns", "rosstat", "procurement", "spk")
            }
        ),
    )

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, content=body, headers={"Content-Type": mime})

    async with DamiaClient(
        settings=settings, http_transport=httpx.MockTransport(handle)
    ) as client:
        call = getattr(getattr(client, service), method)
        if status == 403:
            with pytest.raises(DamiaHTTPError) as caught:
                await call()
            assert caught.value.status_code == status
            diagnostic = (
                str(caught.value)
                + repr(caught.value)
                + "".join(traceback.format_exception(caught.value))
            )
            assert (
                "synthetic-key" not in diagnostic and "synthetic-body" not in diagnostic
            )
        else:
            response = await call()
            assert response.status_code == status and response.body == body
            if mime == "application/json" and expected is None:
                with pytest.raises(DamiaResponseError) as response_caught:
                    _ = response.data
                assert "synthetic-body" not in "".join(
                    traceback.format_exception(response_caught.value)
                )
            else:
                assert response.data == expected
    assert len(requests) == 1 and requests[0].url.path == path
    assert list(requests[0].url.params.multi_items()) == [("key", "synthetic-key")]
