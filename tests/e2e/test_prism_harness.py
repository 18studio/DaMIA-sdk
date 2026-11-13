"""Проверка тестовой инфраструктуры отдельно от нереализованного SDK."""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr

from damia_sdk import BaseURLSettings, DamiaSettings
from damia_sdk.transport import HttpClient

from .conftest import LocalPrism
from .operations import OPERATIONS, Operation


@pytest.mark.e2e
@pytest.mark.parametrize(
    "operation",
    [op for op in OPERATIONS if op.service == "fns" and op.method == "egr"],
    ids=lambda op: op.id,
)
def test_proxy_forwards_to_prism(
    operation: Operation, prism_servers: dict[str, LocalPrism]
) -> None:
    prism = prism_servers[operation.service]
    prism.proxy.clear()
    with httpx.Client(trust_env=False, timeout=10) as client:
        response = client.get(
            prism.proxy.url + operation.path,
            params={"req": "0000000000", "key": "synthetic-key"},
        )
    assert response.status_code == 200
    records = prism.proxy.records()
    assert len(records) == 1
    parsed = urlsplit(records[0].path)
    assert parsed.path == operation.path
    assert parse_qs(parsed.query) == {"req": ["0000000000"], "key": ["synthetic-key"]}
    assert records[0].status == response.status_code
    assert records[0].body == response.content


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [op for op in OPERATIONS if op.service == "fns" and op.method == "egr"],
    ids=lambda op: op.id,
)
async def test_http_core_calls_local_prism(
    operation: Operation, prism_servers: dict[str, LocalPrism]
) -> None:
    prism = prism_servers[operation.service]
    config = DamiaSettings(
        fns_key=SecretStr("synthetic-key"),
        base_urls=BaseURLSettings(fns=prism.proxy.url),
    )
    prism.proxy.clear()
    async with HttpClient(config) as client:
        response = await client.request(
            "GET", operation.path, service="fns", params=[("req", "0000000000")]
        )
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    records = prism.proxy.records()
    assert len(records) == 1
    assert parse_qs(urlsplit(records[0].path).query) == {
        "req": ["0000000000"],
        "key": ["synthetic-key"],
    }
