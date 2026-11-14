import traceback

import pytest

from damia_sdk.exceptions import DamiaResponseError
from damia_sdk.transport import HttpResponse


@pytest.mark.parametrize(
    "constant", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"]
)
@pytest.mark.parametrize(
    "template", ["{}", '{{"marker": "secret-marker", "nested": [0, {{"value": {}}}]}}']
)
@pytest.mark.parametrize("access", ["json", "data"])
def test_nonstandard_json_constants_are_rejected_without_body_leak(
    constant: str, template: str, access: str
) -> None:
    marker = "secret-marker"
    body = template.format(constant).encode()
    response = HttpResponse(200, "application/json", body)
    with pytest.raises(DamiaResponseError) as exc:
        response.json() if access == "json" else response.data
    assert marker not in str(exc.value)
    assert marker not in "".join(traceback.format_exception(exc.value))
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b'"NaN"', "NaN"),
        (b"1.25", 1.25),
        (b"null", None),
        (b"true", True),
        (b'{"items": ["Infinity", -2.5, 3]}', {"items": ["Infinity", -2.5, 3]}),
    ],
)
@pytest.mark.parametrize(
    "mime",
    [
        "application/json",
        "APPLICATION/JSON; charset=utf-8",
        "application/example+json",
        "text/example+json",
    ],
)
def test_valid_json_values(body: bytes, expected: object, mime: str) -> None:
    response = HttpResponse(200, mime, body)
    assert response.json() == expected
    assert response.data == expected


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("text/plain", '{"ok":true}'),
        ("application/octet-stream", b'{"ok":true}'),
        (None, b'{"ok":true}'),
    ],
)
def test_non_json_mime_data(mime: str | None, expected: object) -> None:
    assert HttpResponse(200, mime, b'{"ok":true}').data == expected


def test_invalid_json_does_not_leak_synthetic_body() -> None:
    response = HttpResponse(200, "application/json", b'{"synthetic-marker":')
    with pytest.raises(DamiaResponseError) as exc:
        _ = response.data
    assert "synthetic-marker" not in str(exc.value)
    assert exc.value.__context__ is None


def test_unknown_mime_returns_synthetic_bytes() -> None:
    body = b"\x00\xffsynthetic-file"
    assert HttpResponse(200, "application/x-synthetic", body).data == body
