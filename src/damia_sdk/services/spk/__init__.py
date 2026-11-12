"""Skeleton for the SPK and inspections API."""

from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class SpkService:
    """SPK reports and prosecutor inspections."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def report(
        self,
        *,
        req: str | None = None,
        format: str | None = None,
        sections: str | None = None,
    ) -> NoReturn:
        """Get a comprehensive counterparty report."""
        raise NotImplementedError

    async def proverki(
        self,
        *,
        req: str | None = None,
        status: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        page: int | None = None,
    ) -> NoReturn:
        """Get prosecutor inspections."""
        raise NotImplementedError
