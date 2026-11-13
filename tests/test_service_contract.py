"""Локальная проверка маршрутов и параметров всех операций по OpenAPI.

MockTransport не выполняет сетевых запросов. Спецификации исследовательские;
эти тесты проверяют реализацию SDK относительно них, а не реальный API.
"""

import inspect
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
import yaml
from pydantic import SecretStr

from damia_sdk import BaseURLSettings, DamiaClient, DamiaSettings

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


def cases() -> list[tuple[str, str, str, list[dict[str, Any]]]]:
    result = []
    for service in SERVICES:
        spec = yaml.safe_load(
            (ROOT / "docs" / "swagger" / service / "openapi.yaml").read_text()
        )
        for path, item in spec["paths"].items():
            operation = item.get("get")
            if operation is None:
                continue
            parameters = []
            for raw in operation.get("parameters", []):
                parameter = raw
                if "$ref" in raw:
                    parameter = spec
                    for part in raw["$ref"][2:].split("/"):
                        parameter = parameter[
                            part.replace("~1", "/").replace("~0", "~")
                        ]
                if parameter.get("in") == "query" and parameter["name"] != "key":
                    parameters.append(parameter)
            result.append((service, path.rsplit("/", 1)[-1], path, parameters))
    return result


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
            assert request.url.path == path
            assert request.url.params.get_list(wire_name) == expected
            assert request.url.params.get_list("key") == ["synthetic-contract-key"]
            assert set(request.url.params.keys()) == {wire_name, "key"}
