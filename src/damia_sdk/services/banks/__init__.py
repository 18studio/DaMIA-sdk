"""Skeleton for the API-Банки GET methods."""

from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class BanksService:
    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def bankdata(
        self,
        *,
        bankregn: str | None = None,
        pokid: str | None = None,
        pokname: str | None = None,
        date: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def bankinfo(self, *, bankregn: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def bankaraits(
        self, *, bankregn: str | None = None, date: str | None = None
    ) -> NoReturn:
        raise NotImplementedError

    async def bankbic(self, *, bankbic: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def bankotch(
        self,
        *,
        bankregn: str | None = None,
        poktype: str | None = None,
        date: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def banksrait(
        self,
        *,
        pokid: str | None = None,
        pokname: str | None = None,
        date: str | None = None,
        cond: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def listdata(
        self,
        *,
        groupid: str | None = None,
        pokid: str | None = None,
        pokname: str | None = None,
        date: str | None = None,
        type: str | None = None,
        cond: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def pokinfo(
        self,
        *,
        pokid: str | None = None,
        pokname: str | None = None,
        date: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def stat(self) -> NoReturn:
        raise NotImplementedError
