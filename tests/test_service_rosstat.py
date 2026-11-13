"""Offline contract tests for Rosstat query serialization."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from damia_sdk.services.rosstat import RosstatService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "kwargs", "path", "params"),
    [
        ("balance", {}, "/balance", []),
        ("balance", {"inn": "001"}, "/balance", [("inn", "001")]),
        ("balance", {"inn": ""}, "/balance", [("inn", "")]),
        ("multbalance", {}, "/multbalance", []),
        ("multbalance", {"inn": "001,002"}, "/multbalance", [("inn", "001,002")]),
        (
            "multbalance",
            {"inn_list": ["001", "002", "001"]},
            "/multbalance",
            [("inn[]", "001"), ("inn[]", "002"), ("inn[]", "001")],
        ),
        ("multbalance", {"inn_list": []}, "/multbalance", []),
        ("statcodes", {}, "/statcodes", []),
        (
            "statcodes",
            {"req": "001", "forms": 0},
            "/statcodes",
            [("req", "001"), ("forms", "0")],
        ),
        ("statcodes", {"forms": 1}, "/statcodes", [("forms", "1")]),
    ],
)
async def test_rosstat_requests(
    method: str, kwargs: dict[str, Any], path: str, params: list[tuple[str, str]]
) -> None:
    response = HttpResponse(
        status_code=200, content_type="application/json", body=b"{}"
    )
    transport = AsyncMock(spec=HttpClient)
    transport.request.return_value = response
    service = RosstatService(cast(HttpClient, transport))

    result = await getattr(service, method)(**kwargs)

    assert result is response
    transport.request.assert_awaited_once_with(
        "GET", path, service="rosstat", params=params
    )
