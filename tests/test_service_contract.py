"""Локальная проверка маршрутов и параметров всех операций по OpenAPI.

MockTransport не выполняет сетевых запросов. Спецификации исследовательские;
эти тесты проверяют реализацию SDK относительно них, а не реальный API.
"""

import inspect
import re
import traceback
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
import yaml
from pydantic import SecretStr

from damia_sdk import (
    BaseURLSettings,
    CacheSettings,
    DamiaClient,
    DamiaConfigurationError,
    DamiaHTTPError,
    DamiaSettings,
    RetrySettings,
)

SERVICES = (
    "fns",
    "rosstat",
    "banks",
    "scoring",
    "procurement",
    "arbitration",
    "fssp",
    "spk",
)
ROOT = Path(__file__).resolve().parents[1]


def resolve_parameter(
    spec: dict[str, Any], parameter: dict[str, Any]
) -> dict[str, Any]:
    seen: set[str] = set()
    while "$ref" in parameter:
        ref = parameter["$ref"]
        if (
            not isinstance(ref, str)
            or not ref.startswith("#/")
            or re.search(r"~(?![01])", ref)
        ):
            raise ValueError(f"invalid or external $ref: {ref}")
        if ref in seen:
            raise ValueError(f"cyclic $ref: {ref}")
        seen.add(ref)
        node: Any = spec
        try:
            for token in ref[2:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(node, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", token):
                        raise ValueError(f"unresolved $ref: {ref}")
                    node = node[int(token)]
                else:
                    node = node[token]
        except (IndexError, KeyError, TypeError) as exc:
            raise ValueError(f"unresolved $ref: {ref}") from exc
        if not isinstance(node, dict):
            raise TypeError(f"non-object $ref: {ref}")
        parameter = node
    return parameter


def query_parameters(
    spec: dict[str, Any], item: dict[str, Any]
) -> list[dict[str, Any]]:
    merged = {}
    for raw in item.get("parameters", []) + item["get"].get("parameters", []):
        parameter = resolve_parameter(spec, raw)
        merged[(parameter["name"], parameter["in"])] = parameter
    return [
        p
        for (name, location), p in merged.items()
        if location == "query" and name != "key"
    ]


PATH_ITEM_METADATA = {"parameters", "summary", "description", "servers", "$ref"}


def checked_operations(
    service: str, spec: dict[str, Any], sdk: object
) -> list[tuple[str, str]]:
    result = []
    for path, item in spec["paths"].items():
        for verb in item:
            if verb in PATH_ITEM_METADATA or verb.startswith("x-"):
                continue
            assert verb == "get", f"{service} {path} unsupported verb {verb}"
            method = path.rsplit("/", 1)[-1]
            assert callable(getattr(sdk, method, None)), (
                f"{service} {path} {verb} missing SDK method {method}"
            )
            result.append((path, method))
    return result


def cases() -> list[tuple[str, str, str, list[dict[str, Any]]]]:
    result = []
    for service in SERVICES:
        spec = yaml.safe_load(
            (ROOT / "docs" / "swagger" / service / "openapi.yaml").read_text()
        )
        sdk = getattr(DamiaClient(), service)
        for path, method in checked_operations(service, spec, sdk):
            item = spec["paths"][path]
            if "get" in item:
                result.append(
                    (
                        service,
                        method,
                        path,
                        query_parameters(spec, item),
                    )
                )
    return result


def test_query_parameters_merge_and_references() -> None:
    spec = {"components": {"parameters": {"ref/param": {"name": "ref", "in": "query"}}}}
    item = {
        "parameters": [
            {"name": "path", "in": "query"},
            {"name": "override", "in": "query", "required": True},
            {"$ref": "#/components/parameters/ref~1param"},
            {"name": "key", "in": "query"},
            {"name": "header", "in": "header"},
        ],
        "get": {
            "parameters": [
                {"name": "override", "in": "query", "required": False},
                {"name": "operation", "in": "query"},
            ]
        },
    }
    assert query_parameters(spec, item) == [
        {"name": "path", "in": "query"},
        {"name": "override", "in": "query", "required": False},
        {"name": "ref", "in": "query"},
        {"name": "operation", "in": "query"},
    ]
    for ref in ("https://example.invalid/ref", "#/missing", "#/bad~2escape"):
        with pytest.raises(ValueError):
            resolve_parameter(spec, {"$ref": ref})
    with pytest.raises(ValueError, match="cyclic"):
        resolve_parameter({"loop": {"$ref": "#/loop"}}, {"$ref": "#/loop"})


def test_get_operation_count() -> None:
    entries = cases()
    assert len(entries) == 61
    assert len({(service, path) for service, _, path, _ in entries}) == 61


@pytest.mark.asyncio
@pytest.mark.parametrize(("service", "method_name", "path", "parameters"), cases())
async def test_documented_query_parameters_are_forwarded_individually(
    service: str, method_name: str, path: str, parameters: list[dict[str, Any]]
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    base_urls = BaseURLSettings.model_validate(
        {name: "https://example.invalid" for name in SERVICES}
    )
    secret = SecretStr("synthetic-contract-key")
    settings = DamiaSettings(
        fns_key=secret, banks_key=secret, damia_key=secret, base_urls=base_urls
    )
    async with DamiaClient(
        settings=settings, http_transport=httpx.MockTransport(handle)
    ) as client:
        method = getattr(getattr(client, service), method_name)
        signature = inspect.signature(method)
        # Проверяем отсутствие произвольных значений по умолчанию на проводе.
        result = await method()
        assert result.data == {"ok": True}
        assert requests[-1].method == "GET"
        assert requests[-1].url.path == path
        assert list(requests[-1].url.params.multi_items()) == [
            ("key", "synthetic-contract-key")
        ]

        for parameter in parameters:
            wire_name = parameter["name"]
            python_name = (
                wire_name[:-2] + "_list" if wire_name.endswith("[]") else wire_name
            )
            assert python_name in signature.parameters, (
                service,
                method_name,
                wire_name,
            )
            schema = parameter.get("schema", {})
            annotation = signature.parameters[python_name].annotation
            if schema.get("type") == "array":
                argument: object = ["synthetic-a", "synthetic-b"]
                expected = ["synthetic-a", "synthetic-b"]
            elif schema.get("type") == "integer":
                # Банковские числовые идентификаторы в публичном API SDK — строки.
                argument = "0" if str in get_args(annotation) else 0
                expected = ["0"]
            elif schema.get("enum"):
                argument = schema["enum"][0]
                expected = [str(argument)]
            else:
                argument = "synthetic-value"
                expected = ["synthetic-value"]
            before = len(requests)
            response = await method(**{python_name: argument})
            assert response.status_code == 200
            assert len(requests) == before + 1
            request = requests[-1]
            assert request.method == "GET"
            assert request.url.path == path
            assert request.url.params.get_list(wire_name) == expected
            assert request.url.params.get_list("key") == ["synthetic-contract-key"]
            assert sorted(request.url.params.multi_items()) == sorted(
                [(wire_name, value) for value in expected]
                + [("key", "synthetic-contract-key")]
            )


@pytest.mark.asyncio
async def test_synthetic_combined_parameters_preserve_wire_values() -> None:
    """SDK serialization only; combinations are not validated by the server."""
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"synthetic": True})

    base_urls = BaseURLSettings.model_validate(
        {name: "https://example.invalid" for name in SERVICES}
    )
    secret = SecretStr("synthetic-contract-key")
    settings = DamiaSettings(
        fns_key=secret, banks_key=secret, damia_key=secret, base_urls=base_urls
    )
    async with DamiaClient(
        settings=settings, http_transport=httpx.MockTransport(handle)
    ) as client:
        await client.fns.search(q="Тест 001", page=0, filter="")
        await client.fns.multinfo(req=None, req_list=["001", "тест", ""])
        await client.fns.multinfo(req="", req_list=[])
        await client.banks.bankdata(
            bankregn="000123", pokid="00", pokname="", date=None
        )

    expected = [
        ("/search", [("q", "Тест 001"), ("page", "0"), ("filter", "")]),
        ("/multinfo", [("req[]", "001"), ("req[]", "тест"), ("req[]", "")]),
        ("/multinfo", [("req", "")]),
        ("/api/bankdata", [("bankregn", "000123"), ("pokid", "00"), ("pokname", "")]),
    ]
    assert len(requests) == len(expected)
    for request, (path, parameters) in zip(requests, expected, strict=True):
        assert request.method == "GET"
        assert request.url.path == path
        items = list(request.url.params.multi_items())
        assert [value for name, value in items if name == "key"] == [
            "synthetic-contract-key"
        ]
        assert [(name, value) for name, value in items if name != "key"] == parameters


def synthetic_settings(**kwargs: Any) -> DamiaSettings:
    secret = SecretStr("synthetic-contract-key")
    return DamiaSettings(
        fns_key=secret,
        banks_key=secret,
        damia_key=secret,
        scoring_key=secret,
        base_urls=BaseURLSettings.model_validate(
            {name: "https://example.invalid" for name in SERVICES}
        ),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_serialization_boundaries_multinfo_and_scoring() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async with DamiaClient(
        settings=synthetic_settings(), http_transport=httpx.MockTransport(handle)
    ) as client:
        await client.fns.search(q="Юникод &+=?#/%", page=-5, filter="")
        await client.fns.search(q=None, page=0, filter=None)
        await client.fns.multinfo(req="one")
        await client.fns.multinfo(req_list=[])
        await client.fns.multinfo(req_list=["x", "x", "", "y"])
        await client.fns.multinfo(req="one", req_list=["x", "x"])
        await client.scoring.score(
            inn="001",
            model="m",
            balance_fields={
                "b1000": 0,
                "b2000": -7,
                "arbitrary & name": 9,
                "inn": 2,
                "model": -3,
            },
        )
        before = len(requests)
        with pytest.raises(DamiaConfigurationError) as exc:
            await client.scoring.score(balance_fields={"key": 12345})
        diagnostic = "".join(traceback.format_exception(exc.value))
        assert "synthetic-contract-key" not in diagnostic
        assert len(requests) == before

    expected = [
        ("/search", [("q", "Юникод &+=?#/%"), ("page", "-5"), ("filter", "")]),
        ("/search", [("page", "0")]),
        ("/multinfo", [("req", "one")]),
        ("/multinfo", []),
        ("/multinfo", [("req[]", "x"), ("req[]", "x"), ("req[]", ""), ("req[]", "y")]),
        ("/multinfo", [("req", "one"), ("req[]", "x"), ("req[]", "x")]),
        (
            "/score",
            [
                ("inn", "001"),
                ("inn", "2"),
                ("model", "m"),
                ("model", "-3"),
                ("b1000", "0"),
                ("b2000", "-7"),
                ("arbitrary & name", "9"),
            ],
        ),
    ]
    assert len(requests) == len(expected)
    for request, (path, pairs) in zip(requests, expected, strict=True):
        assert request.method == "GET" and request.url.path == path
        assert list(request.url.params.multi_items()) == pairs + [
            ("key", "synthetic-contract-key")
        ]
        for name in {name for name, _ in pairs} | {"key"}:
            assert request.url.params.get_list(name) == [
                v for n, v in pairs + [("key", "synthetic-contract-key")] if n == name
            ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service", "method", "path"),
    [
        ("fns", "mon", "/mon"),
        ("procurement", "zmon", "/zmon"),
        ("arbitration", "delopro", "/arb/delopro"),
    ],
)
async def test_side_effect_gets_do_not_retry_or_cache(
    service: str, method: str, path: str
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, json={"ok": True})

    settings = synthetic_settings(
        cache=CacheSettings(enabled=True), retry=RetrySettings(enabled=True)
    )
    async with DamiaClient(
        settings=settings, http_transport=httpx.MockTransport(handle)
    ) as client:
        call = getattr(getattr(client, service), method)
        with pytest.raises(DamiaHTTPError):
            await call()
        assert len(requests) == 1
        assert not (await call()).from_cache
        assert not (await call()).from_cache
    assert len(requests) == 3
    assert all(
        request.method == "GET" and request.url.path == path for request in requests
    )
    assert all(
        list(request.url.params.multi_items()) == [("key", "synthetic-contract-key")]
        for request in requests
    )


def test_operation_inventory_rejects_mutations() -> None:
    class SDK:
        good = lambda self: None

    mutation_cases: list[tuple[dict[str, dict[str, Any]], str]] = [
        ({"frobnicate": {}}, "svc /good unsupported verb frobnicate"),
        ({"post": {}}, "svc /good unsupported verb post"),
        ({"get": {}}, "svc /missing get missing SDK method missing"),
    ]
    for item, message in mutation_cases:
        path = "/missing" if "get" in item else "/good"
        with pytest.raises(AssertionError, match=message):
            checked_operations("svc", {"paths": {path: item}}, SDK())
    with pytest.raises(AssertionError, match="missing SDK method good"):
        checked_operations("svc", {"paths": {"/good": {"get": {}}}}, object())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "service,method,name",
    [("rosstat", "multbalance", "inn"), ("fns", "multcheck", "req")],
)
@pytest.mark.parametrize(
    "scalar,values",
    [
        (None, None),
        (None, []),
        ("001%Ю", None),
        (None, ["001", "001", "тест%"]),
        ("001%Ю", ["001", "001", "тест%"]),
    ],
)
async def test_alternative_list_wire_boundaries(
    service: str, method: str, name: str, scalar: str | None, values: list[str] | None
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    async with DamiaClient(
        settings=synthetic_settings(),
        http_transport=httpx.MockTransport(handle),
    ) as client:
        await getattr(getattr(client, service), method)(
            **{name: scalar, name + "_list": values}
        )
    pairs = ([] if scalar is None else [(name, scalar)]) + [
        (name + "[]", v) for v in (values or [])
    ]
    assert len(requests) == 1
    assert requests[0].method == "GET" and requests[0].url.path == "/" + method
    assert list(requests[0].url.params.multi_items()) == pairs + [
        ("key", "synthetic-contract-key")
    ]


def enum_cases() -> list[tuple[str, str, str, str, Any]]:
    return [
        (service, method, path, p["name"], value)
        for service, method, path, params in cases()
        for p in params
        for value in p.get("schema", {}).get("enum", [])
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("service,method,path,name,value", enum_cases())
async def test_each_spec_enum_wire_value(
    service: str, method: str, path: str, name: str, value: Any
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    async with DamiaClient(
        settings=synthetic_settings(),
        http_transport=httpx.MockTransport(handle),
    ) as client:
        call = getattr(getattr(client, service), method)
        python_name = name[:-2] + "_list" if name.endswith("[]") else name
        signature = inspect.signature(call)
        assert python_name in signature.parameters, (
            f"{service} {path} enum {name} missing from SDK signature"
        )
        annotation = signature.parameters[python_name].annotation
        assert type(value) in (annotation, *get_args(annotation)), (
            f"{service} {path} enum {name} value {value!r} mismatches {annotation}"
        )
        await call(**{python_name: value})
    assert requests[0].url.path == path
    assert list(requests[0].url.params.multi_items()) == [
        (name, str(value)),
        ("key", "synthetic-contract-key"),
    ]


def test_exact_path_to_sdk_method_mapping_matches_inventory_snapshot() -> None:
    snapshot = yaml.safe_load((ROOT / "docs/contracts/inventory.yaml").read_text())
    expected = {
        (entry["service"], entry["path"]): entry["sdk_method"]
        for entry in snapshot["operations"]
    }
    actual = {(service, path): method for service, method, path, _ in cases()}
    assert len(expected) == len(actual) == 61
    assert actual == expected
