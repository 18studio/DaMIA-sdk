from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class FNSService:
    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def get_search(self, *, q: str, page: int, filter: str) -> NoReturn:
        raise NotImplementedError

    async def get_ac(self, *, q: str, filter: str) -> NoReturn:
        raise NotImplementedError

    async def get_egr(self, *, req: str) -> NoReturn:
        raise NotImplementedError

    async def get_multinfo(self, *, req: str, req_list: list[str]) -> NoReturn:
        """The req_list parameter corresponds to the query parameter req[]."""
        raise NotImplementedError

    async def get_multcheck(self, *, req: str, req_list: list[str]) -> NoReturn:
        """The req_list parameter corresponds to the query parameter req[]."""
        raise NotImplementedError

    async def get_check(self, *, req: str) -> NoReturn:
        raise NotImplementedError

    async def get_nalogbi(self, *, inn: str) -> NoReturn:
        raise NotImplementedError

    async def get_nalogbi_file(self, *, inn: str, bik: str) -> NoReturn:
        raise NotImplementedError

    async def get_changes(self, *, req: str, dat: str) -> NoReturn:
        raise NotImplementedError

    async def get_mon(
        self, *, cmd: str, req: str, page: int, year: int, dat: str, type: str
    ) -> NoReturn:
        raise NotImplementedError

    async def get_vyp(self, *, req: str) -> NoReturn:
        raise NotImplementedError

    async def get_mspinfo_file(self, *, req: str, type: str) -> NoReturn:
        raise NotImplementedError

    async def get_bo(self, *, req: str) -> NoReturn:
        raise NotImplementedError

    async def get_bo_file(self, *, req: str, year: int, xls: int) -> NoReturn:
        raise NotImplementedError

    async def get_innfl(
        self,
        *,
        fam: str,
        nam: str,
        otch: str,
        bdate: str,
        doctype: str,
        docno: str,
    ) -> NoReturn:
        raise NotImplementedError

    async def get_mvdpass(self, *, docno: str) -> NoReturn:
        raise NotImplementedError

    async def get_mvdinfo(self, *, docno: str) -> NoReturn:
        raise NotImplementedError

    async def get_fl_status(self, *, inn: str, dat: str) -> NoReturn:
        raise NotImplementedError

    async def get_fsrar(
        self, *, inn: str, status: str, kpp: str, page: int
    ) -> NoReturn:
        raise NotImplementedError

    async def get_zsk(self, *, inn: str) -> NoReturn:
        raise NotImplementedError

    async def get_rom(self, *, inn: str) -> NoReturn:
        raise NotImplementedError

    async def get_fias_info(self, *, object_id: str) -> NoReturn:
        raise NotImplementedError

    async def get_fias_search(self, *, q: str) -> NoReturn:
        raise NotImplementedError

    async def get_stat(self) -> NoReturn:
        raise NotImplementedError
