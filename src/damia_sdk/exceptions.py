"""Безопасные для вывода исключения транспорта DaMIA SDK.

Исключения не содержат URL, параметры запроса, ключи или тела ответов.
"""


class DamiaError(Exception):
    """Базовое исключение SDK."""


class DamiaConfigurationError(DamiaError):
    """Некорректная конфигурация или отсутствие ключа сервиса."""


class DamiaClientClosedError(DamiaError):
    """Попытка использовать закрытый клиент."""


class DamiaConnectionError(DamiaError):
    """Ошибка сетевого соединения."""


class DamiaTimeoutError(DamiaConnectionError):
    """Превышено время ожидания запроса или бюджета повторов."""


class DamiaHTTPError(DamiaError):
    """Неуспешный HTTP-статус без сохранения содержимого ответа."""

    def __init__(self, status_code: int, *, retry_after: float | None = None) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(f"API вернул HTTP {status_code}.")


class DamiaRateLimitError(DamiaHTTPError):
    """HTTP 429: ограничение частоты запросов."""


class DamiaResponseError(DamiaError):
    """Ответ не удалось разобрать в ожидаемом формате."""
