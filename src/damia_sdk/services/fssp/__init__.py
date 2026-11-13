"""DaMIA FSSP service operations."""

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


def _params(*values: tuple[str, str | int | None]) -> list[tuple[str, str]]:
    return [(name, str(value)) for name, value in values if value is not None]


class FsspService:
    """FSSP operations; optional arguments do not establish API requirements."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def isp(self, *, regn: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/isp", service="fssp", params=_params(("regn", regn))
        )

    async def isps(
        self,
        *,
        inn: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        format: int | None = None,
        page: int | None = None,
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/isps",
            service="fssp",
            params=_params(
                ("inn", inn),
                ("from_date", from_date),
                ("to_date", to_date),
                ("format", format),
                ("page", page),
            ),
        )

    async def ispfl(self, *, regn: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/ispfl", service="fssp", params=_params(("regn", regn))
        )

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
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/ispsfl",
            service="fssp",
            params=_params(
                ("region", region),
                ("fam", fam),
                ("nam", nam),
                ("otch", otch),
                ("bdate", bdate),
                ("format", format),
                ("page", page),
            ),
        )
