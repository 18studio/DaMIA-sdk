"""Skeleton for the Rosstat API service."""

from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class RosstatService:
    """Rosstat financial reporting and statistical codes."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def balance(self, *, inn: str | None = None) -> NoReturn:
        """GET /balance: financial reports for a legal entity."""
        raise NotImplementedError

    async def multbalance(
        self, *, inn: str | None = None, inn_list: list[str] | None = None
    ) -> NoReturn:
        """GET /multbalance: reports for up to 100 companies.

        ``inn`` (comma-separated) and ``inn_list`` (query parameter ``inn[]``)
        are alternative forms and should not be sent together.
        """
        raise NotImplementedError

    async def statcodes(
        self, *, req: str | None = None, forms: int | None = None
    ) -> NoReturn:
        """GET /statcodes: statistical codes; the documented forms default is 0."""
        raise NotImplementedError
