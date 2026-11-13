"""Procurement API GET operations.

None defaults only allow omission; parameter requirements and server defaults
are not established by this interface.
"""

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


class ProcurementService:
    """Procurement API operations."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def _get(self, path: str, **values: object) -> HttpResponse:
        params = [
            (name, str(value)) for name, value in values.items() if value is not None
        ]
        return await self._transport.request(
            "GET", path, service="procurement", params=params
        )

    async def zakupka(
        self, *, regn: str | None = None, actual: int | None = None
    ) -> HttpResponse:
        """GET /zakupka: procurement notice."""
        return await self._get("/zakupka", regn=regn, actual=actual)

    async def contract(self, *, regn: str | None = None) -> HttpResponse:
        """GET /contract: contract or agreement."""
        return await self._get("/contract", regn=regn)

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
    ) -> HttpResponse:
        """GET /zakupki: procurement participation summary."""
        return await self._get(
            "/zakupki",
            inn=inn,
            fz=fz,
            role=role,
            from_date=from_date,
            to_date=to_date,
            format=format,
            page=page,
        )

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
    ) -> HttpResponse:
        """GET /contracts: contract summary."""
        return await self._get(
            "/contracts",
            inn=inn,
            fz=fz,
            role=role,
            from_date=from_date,
            to_date=to_date,
            format=format,
            page=page,
        )

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
    ) -> HttpResponse:
        """GET /zsearch: search procurements."""
        return await self._get(
            "/zsearch",
            q=q,
            from_date=from_date,
            to_date=to_date,
            region=region,
            okpd=okpd,
            status=status,
            cust_inn=cust_inn,
            placing=placing,
            etp=etp,
            min_price=min_price,
            max_price=max_price,
            smp=smp,
            fz=fz,
            page=page,
        )

    async def customer(self, *, req: str | None = None) -> HttpResponse:
        """GET /customer: customer registry."""
        return await self._get("/customer", req=req)

    async def eruz(self, *, req: str | None = None) -> HttpResponse:
        """GET /eruz: unified participant registry."""
        return await self._get("/eruz", req=req)

    async def zfas(
        self,
        *,
        inn: str | None = None,
        page: int | None = None,
        req: str | None = None,
        format: object = None,
    ) -> HttpResponse:
        """GET /zfas: FAS complaints and inspections.

        The support for req and format, and the type of format, are unconfirmed.
        """
        return await self._get("/zfas", inn=inn, page=page, req=req, format=format)

    async def rnp(self, *, inn: str | None = None) -> HttpResponse:
        """GET /rnp: register of unscrupulous suppliers."""
        return await self._get("/rnp", inn=inn)

    async def sro(self, *, req: str | None = None) -> HttpResponse:
        """GET /sro: self-regulatory organizations and membership."""
        return await self._get("/sro", req=req)

    async def ktru(
        self,
        *,
        q: str | None = None,
        ktru: str | None = None,
        okpd2: str | None = None,
        nkmi: str | None = None,
        page: str | None = None,
    ) -> HttpResponse:
        """GET /ktru: catalog of goods, works and services."""
        return await self._get(
            "/ktru", q=q, ktru=ktru, okpd2=okpd2, nkmi=nkmi, page=page
        )

    async def zmon(
        self,
        *,
        a: str | None = None,
        regn: str | None = None,
        email: str | None = None,
    ) -> HttpResponse:
        """GET /zmon: monitoring; may change subscriptions or email.

        Despite being GET, mutation-capable calls must not be prefetched,
        ordinarily GET-cached, or automatically retried. Testing mutations
        requires separate authorization.
        """
        return await self._get("/zmon", a=a, regn=regn, email=email)
