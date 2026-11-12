"""Scoring API service skeleton."""

from collections.abc import Mapping
from typing import NoReturn

from damia_sdk.transport.http import HttpClient


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
    ) -> NoReturn:
        """Calculate counterparty risk.

        ``balance_fields`` contains separate bNNNN query parameters: reporting
        line codes mapped to year-end amounts in thousands of rubles. Values
        are integers and may be negative. The requirement for inn and model is
        not established.
        """
        raise NotImplementedError

    async def info(self, *, model: str | None = None) -> NoReturn:
        """Get model information; the requirement for model is not established."""
        raise NotImplementedError

    async def fincoefs(
        self,
        *,
        inn: str | None = None,
        okved: str | None = None,
        region: int | None = None,
    ) -> NoReturn:
        """Get financial coefficients and industry or region comparisons.

        The requirement for inn is not established. Omitting okved or region
        uses the company's value; "0" for okved or 0 for region selects all
        industries or regions respectively.
        """
        raise NotImplementedError
