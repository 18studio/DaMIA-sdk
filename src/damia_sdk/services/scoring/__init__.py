"""Scoring API service."""

from collections.abc import Mapping

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


class ScoringService:
    """Async interface to the scoring API."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def score(
        self,
        *,
        inn: str | None = None,
        model: str | None = None,
        balance_fields: Mapping[str, int] | None = None,
    ) -> HttpResponse:
        """Calculate counterparty risk.

        ``balance_fields`` contains separate bNNNN query parameters: reporting
        line codes mapped to year-end amounts in thousands of rubles. Values
        are integers and may be negative. The requirement for inn and model is
        not established.
        """
        params = [
            (name, value)
            for name, value in (("inn", inn), ("model", model))
            if value is not None
        ]
        if balance_fields is not None:
            params.extend((name, str(value)) for name, value in balance_fields.items())
        return await self._transport.request(
            "GET", "/score", service="scoring", params=params
        )

    async def info(self, *, model: str | None = None) -> HttpResponse:
        """Get model information; the requirement for model is not established."""
        params = [("model", model)] if model is not None else []
        return await self._transport.request(
            "GET", "/info", service="scoring", params=params
        )

    async def fincoefs(
        self,
        *,
        inn: str | None = None,
        okved: str | None = None,
        region: int | None = None,
    ) -> HttpResponse:
        """Get financial coefficients and industry or region comparisons.

        The requirement for inn is not established. Omitting okved or region
        uses the company's value; "0" for okved or 0 for region selects all
        industries or regions respectively.
        """
        params = [
            (name, value)
            for name, value in (("inn", inn), ("okved", okved))
            if value is not None
        ]
        if region is not None:
            params.append(("region", str(region)))
        return await self._transport.request(
            "GET", "/fincoefs", service="scoring", params=params
        )
