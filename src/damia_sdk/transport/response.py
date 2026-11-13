"""Результат HTTP-запроса без ссылки на URL и объект запроса."""

import json
import math
from dataclasses import dataclass, field
from typing import TypeAlias, cast

from damia_sdk.exceptions import DamiaResponseError

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)


def _reject_json_constant(value: str) -> None:
    raise ValueError("Недопустимая JSON-константа")


def _finite_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Недопустимое JSON-число")
    return number


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Байты ответа и безопасные метаданные транспорта.

    Данные тела могут содержать конфиденциальную информацию и не входят в repr.
    """

    status_code: int
    content_type: str | None
    body: bytes = field(repr=False)
    from_cache: bool = False

    @property
    def data(self) -> JSONValue | bytes:
        """Вернуть JSON, текст или байты согласно типу содержимого ответа."""
        media_type = (self.content_type or "").split(";", 1)[0].strip().lower()
        if media_type == "application/json" or media_type.endswith("+json"):
            return self.json()
        if media_type.startswith("text/"):
            return self.text
        return self.body

    @property
    def text(self) -> str:
        """Декодировать текст в UTF-8, заменяя некорректные последовательности."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> JSONValue:
        """Разобрать JSON, не раскрывая тело в сообщении об ошибке."""
        try:
            data = json.loads(
                self.body,
                parse_constant=_reject_json_constant,
                parse_float=_finite_json_float,
            )
        except (ValueError, UnicodeDecodeError):
            # Не связывать исключение с JSONDecodeError, содержащим исходный документ.
            pass
        else:
            return cast(JSONValue, data)
        raise DamiaResponseError("Ответ API не является корректным JSON.")
