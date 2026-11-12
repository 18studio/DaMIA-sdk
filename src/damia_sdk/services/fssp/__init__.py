"""Skeleton for the DaMIA FSSP service."""

from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class FsspService:
    """FSSP operations; optional arguments do not establish API requirements."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def isp(self, *, regn: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def isps(
        self,
        *,
        inn: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        format: int | None = None,
        page: int | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def ispfl(self, *, regn: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def ispsfl(
        self,
        *,
        region: int | None = None,
        fam: str | None = None,
        nam: str | None = None,
        otch: str | None = None,
        bdate: str | None = None,
        format: int | None = None,
        page: int | None = None,
    ) -> NoReturn:
        raise NotImplementedError
