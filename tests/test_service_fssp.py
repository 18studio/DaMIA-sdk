"""Isolated tests of the FSSP service's transport contract."""

from typing import Any
from unittest.mock import create_autospec

import pytest

from damia_sdk.services.fssp import FsspService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "arguments", "expected"),
    [
        ("isp", {"regn": "00/1-ИП"}, [("regn", "00/1-ИП")]),
        ("ispfl", {"regn": "00/2-ИП"}, [("regn", "00/2-ИП")]),
        (
            "isps",
            {
                "inn": "000123",
                "from_date": "2024-01-02",
                "to_date": "2024-03-04",
                "format": 1,
                "page": 0,
            },
            [
                ("inn", "000123"),
                ("from_date", "2024-01-02"),
                ("to_date", "2024-03-04"),
                ("format", "1"),
                ("page", "0"),
            ],
        ),
        (
            "ispsfl",
            {
                "region": 0,
                "fam": "Фамилия",
                "nam": "Имя",
                "otch": "Отчество",
                "bdate": "01.02.2000",
                "format": 2,
                "page": 3,
            },
            [
                ("region", "0"),
                ("fam", "Фамилия"),
                ("nam", "Имя"),
                ("otch", "Отчество"),
                ("bdate", "01.02.2000"),
                ("format", "2"),
                ("page", "3"),
            ],
        ),
        (
            "isps",
            {"inn": "", "to_date": "2024-03-04"},
            [("inn", ""), ("to_date", "2024-03-04")],
        ),
        ("ispsfl", {"nam": "Имя", "page": 0}, [("nam", "Имя"), ("page", "0")]),
        ("isp", {}, []),
        ("ispfl", {}, []),
        ("isps", {}, []),
        ("ispsfl", {}, []),
    ],
)
async def test_fssp_transport_contract(
    method: str, arguments: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    transport = create_autospec(HttpClient, instance=True)
    response = HttpResponse(
        status_code=200, content_type="application/json", body=b"{}"
    )
    transport.request.return_value = response
    result = await getattr(FsspService(transport), method)(**arguments)
    assert result is response
    transport.request.assert_awaited_once_with(
        "GET", f"/{method}", service="fssp", params=expected
    )
