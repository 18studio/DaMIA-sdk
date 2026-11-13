"""Isolated contract tests for the SPK service."""

from unittest.mock import create_autospec

import pytest

from damia_sdk.services.spk import SpkService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


@pytest.mark.asyncio
async def test_report() -> None:
    transport = create_autospec(HttpClient, instance=True)
    response = HttpResponse(200, "application/octet-stream", b"document")
    transport.request.return_value = response
    result = await SpkService(transport).report(
        req="synthetic", format="json", sections="fns[1,2],bals"
    )
    assert result is response
    transport.request.assert_awaited_once_with(
        "GET",
        "/report",
        service="spk",
        params=[
            ("req", "synthetic"),
            ("format", "json"),
            ("sections", "fns[1,2],bals"),
        ],
    )


@pytest.mark.asyncio
async def test_proverki() -> None:
    transport = create_autospec(HttpClient, instance=True)
    response = HttpResponse(200, "application/json", b"{}")
    transport.request.return_value = response
    result = await SpkService(transport).proverki(
        req="synthetic",
        status="2",
        from_date="2024-01-01",
        to_date="2024-12-31",
        page=0,
    )
    assert result is response
    transport.request.assert_awaited_once_with(
        "GET",
        "/proverki",
        service="spk",
        params=[
            ("req", "synthetic"),
            ("status", "2"),
            ("from_date", "2024-01-01"),
            ("to_date", "2024-12-31"),
            ("page", "0"),
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["report", "proverki"])
async def test_omitted_parameters(method: str) -> None:
    transport = create_autospec(HttpClient, instance=True)
    service = SpkService(transport)
    await getattr(service, method)()
    transport.request.assert_awaited_once_with(
        "GET", f"/{method}", service="spk", params=[]
    )


@pytest.mark.asyncio
async def test_empty_strings_are_not_omitted() -> None:
    transport = create_autospec(HttpClient, instance=True)
    await SpkService(transport).report(req="", sections="")
    transport.request.assert_awaited_once_with(
        "GET", "/report", service="spk", params=[("req", ""), ("sections", "")]
    )
