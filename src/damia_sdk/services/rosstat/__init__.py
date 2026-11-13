"""Rosstat API service."""

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


class RosstatService:
    """Rosstat financial reporting and statistical codes."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def balance(self, *, inn: str | None = None) -> HttpResponse:
        """GET /balance: financial reports for a legal entity."""
        params = [] if inn is None else [("inn", inn)]
        return await self._transport.request(
            "GET", "/balance", service="rosstat", params=params
        )

    async def multbalance(
        self, *, inn: str | None = None, inn_list: list[str] | None = None
    ) -> HttpResponse:
        """GET /multbalance: reports for up to 100 companies.

        ``inn`` (comma-separated) and ``inn_list`` (query parameter ``inn[]``)
        are alternative forms and should not be sent together.
        """
        params = [] if inn is None else [("inn", inn)]
        if inn_list is not None:
            params.extend(("inn[]", value) for value in inn_list)
        return await self._transport.request(
            "GET", "/multbalance", service="rosstat", params=params
        )

    async def statcodes(
        self, *, req: str | None = None, forms: int | None = None
    ) -> HttpResponse:
        """GET /statcodes: statistical codes; the documented forms default is 0."""
        params = [] if req is None else [("req", req)]
        if forms is not None:
            params.append(("forms", str(forms)))
        return await self._transport.request(
            "GET", "/statcodes", service="rosstat", params=params
        )
