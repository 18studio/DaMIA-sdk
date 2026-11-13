"""Offline contract tests for the banks service."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from damia_sdk.services.banks import BanksService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse

CASES = [
    (
        "bankdata",
        {"bankregn": "12", "pokid": "3", "pokname": "assets", "date": "2024-01-01"},
    ),
    ("bankinfo", {"bankregn": "12"}),
    ("bankaraits", {"bankregn": "12", "date": "2024-01-01"}),
    ("bankbic", {"bankbic": "044525225"}),
    ("bankotch", {"bankregn": "12", "poktype": "group", "date": "2024-01-01"}),
    (
        "banksrait",
        {
            "pokid": "3",
            "pokname": "assets",
            "date": "2024-01-01",
            "cond": "in list (1,2,3)",
        },
    ),
    (
        "listdata",
        {
            "groupid": "2",
            "pokid": "3",
            "pokname": "assets",
            "date": "2024-01-01",
            "type": "avg",
            "cond": "not in list (1,2)",
        },
    ),
    ("pokinfo", {"pokid": "3", "pokname": "assets", "date": "2024-01-01"}),
    ("stat", {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "arguments"), CASES)
async def test_banks_routes_and_parameters(
    method: str, arguments: dict[str, Any]
) -> None:
    response = HttpResponse(
        status_code=200, content_type="application/json", body=b"{}"
    )
    transport = AsyncMock(spec=HttpClient)
    transport.request.return_value = response
    service = BanksService(cast(HttpClient, transport))

    result = await getattr(service, method)(**arguments)

    assert result is response
    transport.request.assert_awaited_once_with(
        "GET", f"/api/{method}", service="banks", params=list(arguments.items())
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "arguments"), CASES)
async def test_banks_omit_none(method: str, arguments: dict[str, Any]) -> None:
    transport = AsyncMock(spec=HttpClient)
    service = BanksService(cast(HttpClient, transport))
    await getattr(service, method)(**dict.fromkeys(arguments))
    transport.request.assert_awaited_once_with(
        "GET", f"/api/{method}", service="banks", params=[]
    )


@pytest.mark.asyncio
async def test_banks_preserve_empty_and_serialize_numeric_values() -> None:
    transport = AsyncMock(spec=HttpClient)
    service = BanksService(cast(HttpClient, transport))
    # Numeric values are serialized even though the public identifier types are strings.
    await service.bankdata(bankregn=0, pokid=42, pokname="")  # type: ignore[arg-type]
    transport.request.assert_awaited_once_with(
        "GET",
        "/api/bankdata",
        service="banks",
        params=[("bankregn", "0"), ("pokid", "42"), ("pokname", "")],
    )
