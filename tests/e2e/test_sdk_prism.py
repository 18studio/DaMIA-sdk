"""E2E SDK: каждый метод вызывается через клиент, а не напрямую через Prism."""

import json
import socket
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from hypothesis import Phase, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, SecretStr

from damia_sdk import BaseURLSettings, DamiaClient, DamiaSettings

from .conftest import LocalPrism
from .operations import OPERATIONS, SERVICES, Operation


@pytest.mark.e2e
def test_sdk_network_guard_is_active(local_network_only: None) -> None:
    with pytest.raises(RuntimeError, match="DNS for external hosts is disabled"):
        socket.getaddrinfo("example.com", 443)


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.id)
@settings(
    max_examples=3,
    deadline=None,
    database=None,
    phases=(Phase.explicit, Phase.generate),
    report_multiple_bugs=False,
)
@given(value=st.text(alphabet="0123456789", min_size=10, max_size=10))
async def test_sdk_method_against_prism(
    operation: Operation, prism_servers: dict[str, LocalPrism], value: str
) -> None:
    key = f"synthetic-key-{value}"
    params: dict[str, str] = {"key": key}
    arguments: dict[str, str | int] = {}
    if operation.query_param is not None:
        params[operation.query_param] = operation.wire_value(value)
        arguments[operation.query_param] = operation.sdk_value(value)
    if operation.service == "spk" and operation.method == "report":
        params["format"] = "json"
        arguments["format"] = "json"

    prism = prism_servers[operation.service]
    # Прямой контроль доказывает, что mock операции работает независимо от SDK.
    async with httpx.AsyncClient(trust_env=False, timeout=10) as baseline:
        expected = await baseline.get(prism.url + operation.path, params=params)
    assert expected.status_code == 200, (
        operation.id,
        expected.status_code,
        expected.text,
    )

    settings_model = DamiaSettings(
        fns_key=SecretStr(key),
        banks_key=SecretStr(key),
        damia_key=SecretStr(key),
        base_urls=BaseURLSettings.model_validate(
            {
                service: prism_servers[service].proxy.url
                if service in prism_servers
                else "http://127.0.0.2:1"
                for service in SERVICES
            }
        ),
    )
    prism.proxy.clear()
    async with DamiaClient(settings=settings_model) as client:
        service = getattr(client, operation.service)
        method = getattr(service, operation.method)
        response = await method(**arguments)

    requests = prism.proxy.records()
    assert len(requests) == 1, f"{operation.id}: ожидался ровно один запрос к Prism"
    parsed = urlsplit(requests[0].path)
    assert parsed.path == operation.path
    forwarded = parse_qs(parsed.query, keep_blank_values=True)
    for name, expected_value in params.items():
        assert forwarded.get(name) == [expected_value], (operation.id, name)
    assert response.status_code == expected.status_code

    # Предполагаемый интерфейс ApiResponse[T] ещё не утверждён; при его выборе
    # контракт этой проверки может потребовать изменения.
    data: Any = response.data
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json", by_alias=True, exclude_unset=True)
    content_type = expected.headers.get("Content-Type", "")
    if "json" in content_type:
        assert data == expected.json()
    elif content_type.startswith("text/"):
        assert data == expected.text
    else:
        assert data == expected.content
    assert requests[0].status == expected.status_code
    assert requests[0].body == expected.content or (
        "json" in content_type and json.loads(requests[0].body) == expected.json()
    )
