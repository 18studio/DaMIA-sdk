"""API-Банки GET methods."""

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


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
    ) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("bankregn", bankregn),
                ("pokid", pokid),
                ("pokname", pokname),
                ("date", date),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/bankdata", service="banks", params=params
        )

    async def bankinfo(self, *, bankregn: str | None = None) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("bankregn", bankregn),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/bankinfo", service="banks", params=params
        )

    async def bankaraits(
        self, *, bankregn: str | None = None, date: str | None = None
    ) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("bankregn", bankregn),
                ("date", date),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/bankaraits", service="banks", params=params
        )

    async def bankbic(self, *, bankbic: str | None = None) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("bankbic", bankbic),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/bankbic", service="banks", params=params
        )

    async def bankotch(
        self,
        *,
        bankregn: str | None = None,
        poktype: str | None = None,
        date: str | None = None,
    ) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("bankregn", bankregn),
                ("poktype", poktype),
                ("date", date),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/bankotch", service="banks", params=params
        )

    async def banksrait(
        self,
        *,
        pokid: str | None = None,
        pokname: str | None = None,
        date: str | None = None,
        cond: str | None = None,
    ) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("pokid", pokid),
                ("pokname", pokname),
                ("date", date),
                ("cond", cond),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/banksrait", service="banks", params=params
        )

    async def listdata(
        self,
        *,
        groupid: str | None = None,
        pokid: str | None = None,
        pokname: str | None = None,
        date: str | None = None,
        type: str | None = None,
        cond: str | None = None,
    ) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("groupid", groupid),
                ("pokid", pokid),
                ("pokname", pokname),
                ("date", date),
                ("type", type),
                ("cond", cond),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/listdata", service="banks", params=params
        )

    async def pokinfo(
        self,
        *,
        pokid: str | None = None,
        pokname: str | None = None,
        date: str | None = None,
    ) -> HttpResponse:
        params = [
            (name, str(value))
            for name, value in [
                ("pokid", pokid),
                ("pokname", pokname),
                ("date", date),
            ]
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/api/pokinfo", service="banks", params=params
        )

    async def stat(self) -> HttpResponse:
        params: list[tuple[str, str]] = []
        return await self._transport.request(
            "GET", "/api/stat", service="banks", params=params
        )
