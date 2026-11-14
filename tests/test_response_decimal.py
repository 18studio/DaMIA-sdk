"""Локальный opt-in JSON-разбор без изменения существующего ответа."""

import traceback
from decimal import Decimal

import pytest

from damia_sdk.exceptions import DamiaResponseError
from damia_sdk.transport import DecimalJSONValue, HttpResponse


def test_json_decimal_preserves_values_and_existing_response() -> None:
    body = (
        b'{"id":"000123","unknown":{"items":[123456789012345678901234567890,'
        b'0.12345678901234567890123456789,null,true]},"duplicate":1,"duplicate":2}'
    )
    response = HttpResponse(200, "application/json", body)
    original = response.json()
    result: DecimalJSONValue = response.json_decimal()
    assert isinstance(result, dict)
    assert result["id"] == "000123"
    assert result["unknown"] == {
        "items": [
            123456789012345678901234567890,
            Decimal("0.12345678901234567890123456789"),
            None,
            True,
        ]
    }
    assert "missing" not in result and result["duplicate"] == 2
    assert isinstance(result["unknown"], dict)
    items = result["unknown"]["items"]
    assert isinstance(items, list) and items[2] is None
    assert isinstance(items[0], int) and isinstance(items[1], Decimal)
    assert (
        response.body == body
        and response.json() == original
        and response.data == original
    )


def test_json_decimal_preserves_dynamic_wire_names_and_extensions() -> None:
    body = (
        '{"карта":{"00001":{"Сумма":"001.2300","Идентификатор":"00042",'
        '"неизвестное":{"вложение":[null,0.10000000000000000001]}},'
        '"00002":{"Сумма":null,"целое":123456789012345678901234567890}},'
        '"повтор":"первый","повтор":"последний"}'
    ).encode()
    response = HttpResponse(200, "application/json", body)
    original = response.json()
    result = response.json_decimal()
    assert isinstance(result, dict)
    assert result == {
        "карта": {
            "00001": {
                "Сумма": "001.2300",
                "Идентификатор": "00042",
                "неизвестное": {"вложение": [None, Decimal("0.10000000000000000001")]},
            },
            "00002": {"Сумма": None, "целое": 123456789012345678901234567890},
        },
        "повтор": "последний",
    }
    assert isinstance(result["карта"], dict)
    assert isinstance(result["карта"]["00002"], dict)
    assert "Идентификатор" not in result["карта"]["00002"]
    assert response.body == body
    assert body.count('"повтор"'.encode()) == 2
    assert response.json() == original and response.data == original


def test_json_decimal_ignores_mime_without_changing_data() -> None:
    body = b'{"value":1.20}'
    response = HttpResponse(200, "application/octet-stream", body)
    assert response.data == body
    assert response.json_decimal() == {"value": Decimal("1.20")}
    assert response.data == body


@pytest.mark.parametrize("number", ["1e999", "1e-999", "-1.25e+999999"])
def test_json_decimal_large_exponents(number: str) -> None:
    assert HttpResponse(200, None, number.encode()).json_decimal() == Decimal(number)


@pytest.mark.parametrize(
    "body",
    [
        b'{"synthetic-secret":',
        b'"synthetic-secret\xff"',
        b"\x00\xffsynthetic-secret",
        b'{"synthetic-secret":NaN}',
        b'{"synthetic-secret":Infinity}',
        b'{"synthetic-secret":-Infinity}',
        b'{"synthetic-secret":1e99999999999999999999}',
    ],
)
def test_json_decimal_errors_do_not_expose_body_or_parser(body: bytes) -> None:
    with pytest.raises(DamiaResponseError) as caught:
        HttpResponse(200, None, body).json_decimal()
    error = caught.value
    assert error.__cause__ is None and error.__context__ is None
    assert "synthetic-secret" not in str(error) + repr(error)
    assert "synthetic-secret" not in "".join(traceback.format_exception(error))


def test_json_decimal_preserves_caller_exception_context() -> None:
    try:
        raise ValueError("synthetic-external")
    except ValueError as outer:
        with pytest.raises(DamiaResponseError) as caught:
            HttpResponse(200, None, b"invalid").json_decimal()
        assert caught.value.__context__ is outer
        assert caught.value.__cause__ is None
