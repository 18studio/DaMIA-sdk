"""Isolated request-contract tests for the scoring service."""

from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from damia_sdk.services.scoring import ScoringService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["score", "info", "fincoefs"])
async def test_scoring_methods_omit_unspecified_parameters(method: str) -> None:
    response = HttpResponse(
        status_code=200, content_type="application/json", body=b"{}"
    )
    request = AsyncMock(return_value=response)
    service = ScoringService(cast(HttpClient, Mock(request=request)))

    result = await getattr(service, method)()

    assert result is response
    request.assert_awaited_once_with("GET", f"/{method}", service="scoring", params=[])


@pytest.mark.asyncio
async def test_score_serializes_balance_fields_as_individual_parameters() -> None:
    response = HttpResponse(status_code=200, content_type=None, body=b"response")
    request = AsyncMock(return_value=response)
    service = ScoringService(cast(HttpClient, Mock(request=request)))

    result = await service.score(
        inn="0012345678",
        model="custom model",
        balance_fields={"b1100": 0, "b1300": -100},
    )

    assert result is response
    request.assert_awaited_once_with(
        "GET",
        "/score",
        service="scoring",
        params=[
            ("inn", "0012345678"),
            ("model", "custom model"),
            ("b1100", "0"),
            ("b1300", "-100"),
        ],
    )


@pytest.mark.asyncio
async def test_info_serializes_model() -> None:
    request = AsyncMock()
    service = ScoringService(cast(HttpClient, Mock(request=request)))

    result = await service.info(model="_bankrots2016")

    assert result is request.return_value
    request.assert_awaited_once_with(
        "GET", "/info", service="scoring", params=[("model", "_bankrots2016")]
    )


@pytest.mark.asyncio
async def test_fincoefs_serializes_zero_and_optional_values() -> None:
    request = AsyncMock()
    service = ScoringService(cast(HttpClient, Mock(request=request)))

    result = await service.fincoefs(inn="0012345678", okved="0", region=0)

    assert result is request.return_value
    request.assert_awaited_once_with(
        "GET",
        "/fincoefs",
        service="scoring",
        params=[("inn", "0012345678"), ("okved", "0"), ("region", "0")],
    )
