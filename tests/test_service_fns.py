"""Contract tests for FNS GET methods without network access."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from damia_sdk.services.fns import FNSService
from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse

CASES: list[tuple[str, dict[str, Any], list[tuple[str, str]]]] = [
    (
        "search",
        {"q": "тест", "page": 0, "filter": ""},
        [("q", "тест"), ("page", "0"), ("filter", "")],
    ),
    ("ac", {"q": "x", "filter": "f"}, [("q", "x"), ("filter", "f")]),
    ("egr", {"req": "x"}, [("req", "x")]),
    (
        "multinfo",
        {"req": "x", "req_list": ["a", "a", "b"]},
        [("req", "x"), ("req[]", "a"), ("req[]", "a"), ("req[]", "b")],
    ),
    (
        "multcheck",
        {"req": "x", "req_list": ["a", "b"]},
        [("req", "x"), ("req[]", "a"), ("req[]", "b")],
    ),
    ("check", {"req": "x"}, [("req", "x")]),
    ("nalogbi", {"inn": "x"}, [("inn", "x")]),
    ("nalogbi_file", {"inn": "x", "bik": "y"}, [("inn", "x"), ("bik", "y")]),
    ("changes", {"req": "x", "dat": "d"}, [("req", "x"), ("dat", "d")]),
    (
        "mon",
        {"cmd": "add", "req": "x", "page": 0, "year": 2024, "dat": "d", "type": "t"},
        [
            ("cmd", "add"),
            ("req", "x"),
            ("page", "0"),
            ("year", "2024"),
            ("dat", "d"),
            ("type", "t"),
        ],
    ),
    ("vyp", {"req": "x"}, [("req", "x")]),
    ("mspinfo_file", {"req": "x", "type": "t"}, [("req", "x"), ("type", "t")]),
    ("bo", {"req": "x"}, [("req", "x")]),
    (
        "bo_file",
        {"req": "x", "year": 2024, "xls": 0},
        [("req", "x"), ("year", "2024"), ("xls", "0")],
    ),
    (
        "innfl",
        {
            "fam": "f",
            "nam": "n",
            "otch": "o",
            "bdate": "d",
            "doctype": "t",
            "docno": "z",
        },
        [
            ("fam", "f"),
            ("nam", "n"),
            ("otch", "o"),
            ("bdate", "d"),
            ("doctype", "t"),
            ("docno", "z"),
        ],
    ),
    ("mvdpass", {"docno": "x"}, [("docno", "x")]),
    ("mvdinfo", {"docno": "x"}, [("docno", "x")]),
    ("fl_status", {"inn": "x", "dat": "d"}, [("inn", "x"), ("dat", "d")]),
    (
        "fsrar",
        {"inn": "x", "status": "s", "kpp": "k", "page": 2},
        [("inn", "x"), ("status", "s"), ("kpp", "k"), ("page", "2")],
    ),
    ("zsk", {"inn": "x"}, [("inn", "x")]),
    ("rom", {"inn": "x"}, [("inn", "x")]),
    ("fias_info", {"object_id": "x"}, [("object_id", "x")]),
    ("fias_search", {"q": "x"}, [("q", "x")]),
    ("stat", {}, []),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "arguments", "params"), CASES)
async def test_get_contract(
    name: str, arguments: dict[str, Any], params: list[tuple[str, str]]
) -> None:
    response = HttpResponse(200, "application/json", b'{"ok":true}')
    transport = AsyncMock(spec=HttpClient)
    transport.request.return_value = response
    service = FNSService(cast(HttpClient, transport))
    assert await getattr(service, name)(**arguments) is response
    transport.request.assert_awaited_once_with(
        "GET", f"/{name}", service="fns", params=params
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "arguments", "params"), CASES)
async def test_none_omitted(
    name: str, arguments: dict[str, Any], params: list[tuple[str, str]]
) -> None:
    transport = AsyncMock(spec=HttpClient)
    service = FNSService(cast(HttpClient, transport))
    await getattr(service, name)(**dict.fromkeys(arguments))
    transport.request.assert_awaited_once_with(
        "GET", f"/{name}", service="fns", params=[]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["multinfo", "multcheck"])
async def test_empty_list(name: str) -> None:
    transport = AsyncMock(spec=HttpClient)
    service = FNSService(cast(HttpClient, transport))
    await getattr(service, name)(req_list=[])
    transport.request.assert_awaited_once_with(
        "GET", f"/{name}", service="fns", params=[]
    )
