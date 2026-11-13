"""Асинхронные методы API-ФНС."""

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


def _params(values: list[tuple[str, str | int | None]]) -> list[tuple[str, str]]:
    return [(name, str(value)) for name, value in values if value is not None]


class FNSService:
    """Методы ФНС.

    ``None`` для параметров означает, что обязательность не подтверждена;
    это не утверждение, что реальный API допускает пропуск параметра.
    """

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def search(
        self,
        *,
        q: str | None = None,
        page: int | None = None,
        filter: str | None = None,
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/search",
            service="fns",
            params=_params([("q", q), ("page", page), ("filter", filter)]),
        )

    async def ac(
        self, *, q: str | None = None, filter: str | None = None
    ) -> HttpResponse:
        return await self._transport.request(
            "GET", "/ac", service="fns", params=_params([("q", q), ("filter", filter)])
        )

    async def egr(self, *, req: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/egr", service="fns", params=_params([("req", req)])
        )

    async def multinfo(
        self, *, req: str | None = None, req_list: list[str] | None = None
    ) -> HttpResponse:
        """``req`` и ``req_list`` (wire-имя ``req[]``) — альтернативы."""
        return await self._transport.request(
            "GET",
            "/multinfo",
            service="fns",
            params=_params(
                [("req", req), *[("req[]", value) for value in (req_list or [])]]
            ),
        )

    async def multcheck(
        self, *, req: str | None = None, req_list: list[str] | None = None
    ) -> HttpResponse:
        """``req`` и ``req_list`` (wire-имя ``req[]``) — альтернативы."""
        return await self._transport.request(
            "GET",
            "/multcheck",
            service="fns",
            params=_params(
                [("req", req), *[("req[]", value) for value in (req_list or [])]]
            ),
        )

    async def check(self, *, req: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/check", service="fns", params=_params([("req", req)])
        )

    async def nalogbi(self, *, inn: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/nalogbi", service="fns", params=_params([("inn", inn)])
        )

    async def nalogbi_file(
        self, *, inn: str | None = None, bik: str | None = None
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/nalogbi_file",
            service="fns",
            params=_params([("inn", inn), ("bik", bik)]),
        )

    async def changes(
        self, *, req: str | None = None, dat: str | None = None
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/changes",
            service="fns",
            params=_params([("req", req), ("dat", dat)]),
        )

    async def mon(
        self,
        *,
        cmd: str | None = None,
        req: str | None = None,
        page: int | None = None,
        year: int | None = None,
        dat: str | None = None,
        type: str | None = None,
    ) -> HttpResponse:
        """Команды add и del меняют список мониторинга даже через GET."""
        return await self._transport.request(
            "GET",
            "/mon",
            service="fns",
            params=_params(
                [
                    ("cmd", cmd),
                    ("req", req),
                    ("page", page),
                    ("year", year),
                    ("dat", dat),
                    ("type", type),
                ]
            ),
        )

    async def vyp(self, *, req: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/vyp", service="fns", params=_params([("req", req)])
        )

    async def mspinfo_file(
        self, *, req: str | None = None, type: str | None = None
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/mspinfo_file",
            service="fns",
            params=_params([("req", req), ("type", type)]),
        )

    async def bo(self, *, req: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/bo", service="fns", params=_params([("req", req)])
        )

    async def bo_file(
        self, *, req: str | None = None, year: int | None = None, xls: int | None = None
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/bo_file",
            service="fns",
            params=_params([("req", req), ("year", year), ("xls", xls)]),
        )

    async def innfl(
        self,
        *,
        fam: str | None = None,
        nam: str | None = None,
        otch: str | None = None,
        bdate: str | None = None,
        doctype: str | None = None,
        docno: str | None = None,
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/innfl",
            service="fns",
            params=_params(
                [
                    ("fam", fam),
                    ("nam", nam),
                    ("otch", otch),
                    ("bdate", bdate),
                    ("doctype", doctype),
                    ("docno", docno),
                ]
            ),
        )

    async def mvdpass(self, *, docno: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/mvdpass", service="fns", params=_params([("docno", docno)])
        )

    async def mvdinfo(self, *, docno: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/mvdinfo", service="fns", params=_params([("docno", docno)])
        )

    async def fl_status(
        self, *, inn: str | None = None, dat: str | None = None
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/fl_status",
            service="fns",
            params=_params([("inn", inn), ("dat", dat)]),
        )

    async def fsrar(
        self,
        *,
        inn: str | None = None,
        status: str | None = None,
        kpp: str | None = None,
        page: int | None = None,
    ) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/fsrar",
            service="fns",
            params=_params(
                [("inn", inn), ("status", status), ("kpp", kpp), ("page", page)]
            ),
        )

    async def zsk(self, *, inn: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/zsk", service="fns", params=_params([("inn", inn)])
        )

    async def rom(self, *, inn: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/rom", service="fns", params=_params([("inn", inn)])
        )

    async def fias_info(self, *, object_id: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET",
            "/fias_info",
            service="fns",
            params=_params([("object_id", object_id)]),
        )

    async def fias_search(self, *, q: str | None = None) -> HttpResponse:
        return await self._transport.request(
            "GET", "/fias_search", service="fns", params=_params([("q", q)])
        )

    async def stat(self) -> HttpResponse:
        return await self._transport.request(
            "GET", "/stat", service="fns", params=_params([])
        )
