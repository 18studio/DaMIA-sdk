"""Offline contract tests for procurement service requests."""

from typing import cast
from unittest.mock import AsyncMock

import pytest

from damia_sdk.services.procurement import ProcurementService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse

CASES = [
    ("zakupka", {"regn": "R", "actual": 0}, [("regn", "R"), ("actual", "0")]),
    ("contract", {"regn": "R"}, [("regn", "R")]),
    (
        "zakupki",
        {
            "inn": "I",
            "fz": "44",
            "role": "0",
            "from_date": "a",
            "to_date": "b",
            "format": 2,
            "page": 0,
        },
        [
            ("inn", "I"),
            ("fz", "44"),
            ("role", "0"),
            ("from_date", "a"),
            ("to_date", "b"),
            ("format", "2"),
            ("page", "0"),
        ],
    ),
    (
        "contracts",
        {
            "inn": "I",
            "fz": "223",
            "role": "1",
            "from_date": "a",
            "to_date": "b",
            "format": 1,
            "page": 3,
        },
        [
            ("inn", "I"),
            ("fz", "223"),
            ("role", "1"),
            ("from_date", "a"),
            ("to_date", "b"),
            ("format", "1"),
            ("page", "3"),
        ],
    ),
    (
        "zsearch",
        {
            "q": "a,b",
            "from_date": "a",
            "to_date": "b",
            "region": "1,2",
            "okpd": "x",
            "status": "1",
            "cust_inn": "I",
            "placing": "1,2",
            "etp": "3,4",
            "min_price": 0,
            "max_price": 10,
            "smp": 1,
            "fz": 44,
            "page": 2,
        },
        [
            ("q", "a,b"),
            ("from_date", "a"),
            ("to_date", "b"),
            ("region", "1,2"),
            ("okpd", "x"),
            ("status", "1"),
            ("cust_inn", "I"),
            ("placing", "1,2"),
            ("etp", "3,4"),
            ("min_price", "0"),
            ("max_price", "10"),
            ("smp", "1"),
            ("fz", "44"),
            ("page", "2"),
        ],
    ),
    ("customer", {"req": "R"}, [("req", "R")]),
    ("eruz", {"req": "R"}, [("req", "R")]),
    (
        "zfas",
        {"inn": "I", "page": 2, "req": "R", "format": 2},
        [("inn", "I"), ("page", "2"), ("req", "R"), ("format", "2")],
    ),
    ("rnp", {"inn": "I"}, [("inn", "I")]),
    ("sro", {"req": "R"}, [("req", "R")]),
    (
        "ktru",
        {"q": "a,b", "ktru": "K", "okpd2": "O", "nkmi": "N", "page": "02"},
        [("q", "a,b"), ("ktru", "K"), ("okpd2", "O"), ("nkmi", "N"), ("page", "02")],
    ),
    (
        "zmon",
        {"a": "list", "regn": "R", "email": "synthetic@example.invalid"},
        [("a", "list"), ("regn", "R"), ("email", "synthetic@example.invalid")],
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "values", "params"), CASES)
async def test_procurement_request(
    method: str, values: dict[str, object], params: list[tuple[str, str]]
) -> None:
    response = HttpResponse(
        status_code=201, content_type="text/plain", body=b"synthetic"
    )
    transport = AsyncMock(spec=HttpClient)
    transport.request.return_value = response
    service = ProcurementService(cast(HttpClient, transport))
    result = await getattr(service, method)(**values)
    assert result is response
    transport.request.assert_awaited_once_with(
        "GET", f"/{method}", service="procurement", params=params
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", [case[0] for case in CASES])
async def test_procurement_omits_none(method: str) -> None:
    transport = AsyncMock(spec=HttpClient)
    service = ProcurementService(cast(HttpClient, transport))
    await getattr(service, method)()
    transport.request.assert_awaited_once_with(
        "GET", f"/{method}", service="procurement", params=[]
    )
