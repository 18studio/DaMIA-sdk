"""Skeleton for the procurement API's GET operations.

None defaults only allow omission; parameter requirements and server defaults
are not established by this interface.
"""

from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class ProcurementService:
    """Procurement API operations (not yet implemented)."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def zakupka(
        self, *, regn: str | None = None, actual: int | None = None
    ) -> NoReturn:
        """GET /zakupka: procurement notice."""
        raise NotImplementedError

    async def contract(self, *, regn: str | None = None) -> NoReturn:
        """GET /contract: contract or agreement."""
        raise NotImplementedError

    async def zakupki(
        self,
        *,
        inn: str | None = None,
        fz: str | None = None,
        role: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        format: int | None = None,
        page: int | None = None,
    ) -> NoReturn:
        """GET /zakupki: procurement participation summary."""
        raise NotImplementedError

    async def contracts(
        self,
        *,
        inn: str | None = None,
        fz: str | None = None,
        role: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        format: int | None = None,
        page: int | None = None,
    ) -> NoReturn:
        """GET /contracts: contract summary."""
        raise NotImplementedError

    async def zsearch(
        self,
        *,
        q: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        region: str | None = None,
        okpd: str | None = None,
        status: str | None = None,
        cust_inn: str | None = None,
        placing: str | None = None,
        etp: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        smp: int | None = None,
        fz: int | None = None,
        page: int | None = None,
    ) -> NoReturn:
        """GET /zsearch: search procurements."""
        raise NotImplementedError

    async def customer(self, *, req: str | None = None) -> NoReturn:
        """GET /customer: customer registry."""
        raise NotImplementedError

    async def eruz(self, *, req: str | None = None) -> NoReturn:
        """GET /eruz: unified participant registry."""
        raise NotImplementedError

    async def zfas(
        self,
        *,
        inn: str | None = None,
        page: int | None = None,
        req: str | None = None,
        format: object = None,
    ) -> NoReturn:
        """GET /zfas: FAS complaints and inspections.

        The support for req and format, and the type of format, are unconfirmed.
        """
        raise NotImplementedError

    async def rnp(self, *, inn: str | None = None) -> NoReturn:
        """GET /rnp: register of unscrupulous suppliers."""
        raise NotImplementedError

    async def sro(self, *, req: str | None = None) -> NoReturn:
        """GET /sro: self-regulatory organizations and membership."""
        raise NotImplementedError

    async def ktru(
        self,
        *,
        q: str | None = None,
        ktru: str | None = None,
        okpd2: str | None = None,
        nkmi: str | None = None,
        page: str | None = None,
    ) -> NoReturn:
        """GET /ktru: catalog of goods, works and services."""
        raise NotImplementedError

    async def zmon(
        self,
        *,
        a: str | None = None,
        regn: str | None = None,
        email: str | None = None,
    ) -> NoReturn:
        """GET /zmon: monitoring; may change subscriptions or email.

        Despite being GET, mutation-capable calls must not be prefetched,
        ordinarily GET-cached, or automatically retried. Testing mutations
        requires separate authorization.
        """
        raise NotImplementedError
