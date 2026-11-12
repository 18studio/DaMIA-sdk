"""Асинхронные заготовки методов API-ФНС."""

from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class FNSService:
    """Методы ФНС без сетевой реализации.

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
    ) -> NoReturn:
        raise NotImplementedError

    async def ac(self, *, q: str | None = None, filter: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def egr(self, *, req: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def multinfo(
        self, *, req: str | None = None, req_list: list[str] | None = None
    ) -> NoReturn:
        """``req`` и ``req_list`` (wire-имя ``req[]``) — альтернативы."""
        raise NotImplementedError

    async def multcheck(
        self, *, req: str | None = None, req_list: list[str] | None = None
    ) -> NoReturn:
        """``req`` и ``req_list`` (wire-имя ``req[]``) — альтернативы."""
        raise NotImplementedError

    async def check(self, *, req: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def nalogbi(self, *, inn: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def nalogbi_file(
        self, *, inn: str | None = None, bik: str | None = None
    ) -> NoReturn:
        raise NotImplementedError

    async def changes(
        self, *, req: str | None = None, dat: str | None = None
    ) -> NoReturn:
        raise NotImplementedError

    async def mon(
        self,
        *,
        cmd: str | None = None,
        req: str | None = None,
        page: int | None = None,
        year: int | None = None,
        dat: str | None = None,
        type: str | None = None,
    ) -> NoReturn:
        """Команды add и del меняют список мониторинга даже через GET."""
        raise NotImplementedError

    async def vyp(self, *, req: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def mspinfo_file(
        self, *, req: str | None = None, type: str | None = None
    ) -> NoReturn:
        raise NotImplementedError

    async def bo(self, *, req: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def bo_file(
        self, *, req: str | None = None, year: int | None = None, xls: int | None = None
    ) -> NoReturn:
        raise NotImplementedError

    async def innfl(
        self,
        *,
        fam: str | None = None,
        nam: str | None = None,
        otch: str | None = None,
        bdate: str | None = None,
        doctype: str | None = None,
        docno: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def mvdpass(self, *, docno: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def mvdinfo(self, *, docno: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def fl_status(
        self, *, inn: str | None = None, dat: str | None = None
    ) -> NoReturn:
        raise NotImplementedError

    async def fsrar(
        self,
        *,
        inn: str | None = None,
        status: str | None = None,
        kpp: str | None = None,
        page: int | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def zsk(self, *, inn: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def rom(self, *, inn: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def fias_info(self, *, object_id: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def fias_search(self, *, q: str | None = None) -> NoReturn:
        raise NotImplementedError

    async def stat(self) -> NoReturn:
        raise NotImplementedError
