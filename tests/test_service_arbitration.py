"""Isolated request-contract tests for arbitration operations."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from damia_sdk.services.arbitration import ArbitrationService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


@pytest.mark.parametrize(
    ("method", "kwargs", "params"),
    [
        ("delo", {"regn": "А40-123"}, [("regn", "А40-123")]),
        (
            "delopro",
            {"a": "email", "email": "test@example.invalid"},
            [("a", "email"), ("email", "test@example.invalid")],
        ),
        (
            "dela",
            {
                "q": "name",
                "role": "1",
                "type": "2",
                "status": "3",
                "from_date": "2020-01-01",
                "to_date": "2021-01-01",
                "exact": 0,
                "format": 2,
                "page": 0,
            },
            [
                ("q", "name"),
                ("role", "1"),
                ("type", "2"),
                ("status", "3"),
                ("from_date", "2020-01-01"),
                ("to_date", "2021-01-01"),
                ("exact", "0"),
                ("format", "2"),
                ("page", "0"),
            ],
        ),
        (
            "dsearch",
            {
                "type": "3",
                "status": "1",
                "court": "A40",
                "min_summa": 0,
                "max_summa": 100,
                "from_date": "2020-01-01",
                "to_date": "2021-01-01",
                "page": 2,
            },
            [
                ("type", "3"),
                ("status", "1"),
                ("court", "A40"),
                ("min_summa", "0"),
                ("max_summa", "100"),
                ("from_date", "2020-01-01"),
                ("to_date", "2021-01-01"),
                ("page", "2"),
            ],
        ),
    ],
)
@pytest.mark.asyncio
async def test_arbitration_request(
    method: str, kwargs: dict[str, Any], params: list[tuple[str, str]]
) -> None:
    response = HttpResponse(200, "application/json", b"{}")
    transport = AsyncMock(spec=HttpClient)
    transport.request.return_value = response
    service = ArbitrationService(cast(HttpClient, transport))

    result = await getattr(service, method)(**kwargs)

    assert result is response
    transport.request.assert_awaited_once_with(
        "GET", f"/arb/{method}", service="arbitration", params=params
    )


@pytest.mark.parametrize("method", ["delo", "delopro", "dela", "dsearch"])
@pytest.mark.asyncio
async def test_arbitration_omits_none(method: str) -> None:
    transport = AsyncMock(spec=HttpClient)
    service = ArbitrationService(cast(HttpClient, transport))

    await getattr(service, method)()

    transport.request.assert_awaited_once_with(
        "GET", f"/arb/{method}", service="arbitration", params=[]
    )
