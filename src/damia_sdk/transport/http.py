"""Общий асинхронный HTTP-транспорт DaMIA.

Ключи передаются в query согласно документированному GET-транспорту и видны
серверу, прокси и средствам перехвата трафика. Базовый URL считается доверенным.
DEBUG-логи нижележащих библиотек и сбор локальных переменных traceback требуют
отдельной настройки приложения. SDK не настраивает стороннее логирование.
"""

import asyncio
import hashlib
import hmac
import json
import math
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Literal, Self
from urllib.parse import urlsplit

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from damia_sdk.exceptions import (
    DamiaClientClosedError,
    DamiaConfigurationError,
    DamiaConnectionError,
    DamiaError,
    DamiaHTTPError,
    DamiaRateLimitError,
    DamiaTimeoutError,
)
from damia_sdk.settings import DamiaSettings
from damia_sdk.transport.cache import ResponseCache
from damia_sdk.transport.response import HttpResponse

ServiceName = Literal[
    "fns", "rosstat", "banks", "scoring", "procurement", "arbitration", "fssp", "spk"
]
CacheValidator = Callable[[HttpResponse], bool]

# Разрешённые для явного повтора пути: только известные документированные GET,
# не включая мониторинг и другие изменяющие состояние методы.
_RETRY_PATHS: dict[str, frozenset[str]] = {
    "fns": frozenset(
        {
            "/search",
            "/ac",
            "/egr",
            "/multinfo",
            "/multcheck",
            "/check",
            "/nalogbi",
            "/nalogbi_file",
            "/changes",
            "/vyp",
            "/mspinfo_file",
            "/bo",
            "/bo_file",
            "/innfl",
            "/mvdpass",
            "/mvdinfo",
            "/fl_status",
            "/fsrar",
            "/rom",
            "/fias_info",
            "/fias_search",
            "/stat",
        }
    ),
    "rosstat": frozenset({"/balance", "/multbalance", "/statcodes"}),
    "banks": frozenset(
        {
            "/api/bankdata",
            "/api/bankinfo",
            "/api/bankaraits",
            "/api/bankbic",
            "/api/bankotch",
            "/api/banksrait",
            "/api/listdata",
            "/api/pokinfo",
            "/api/stat",
        }
    ),
    "scoring": frozenset({"/score", "/info", "/fincoefs"}),
    "procurement": frozenset(
        {
            "/zakupka",
            "/contract",
            "/zakupki",
            "/contracts",
            "/zsearch",
            "/customer",
            "/eruz",
            "/zfas",
            "/rnp",
            "/sro",
            "/ktru",
        }
    ),
    "arbitration": frozenset({"/arb/delo", "/arb/dela", "/arb/dsearch"}),
    "fssp": frozenset({"/isp", "/isps", "/ispfl", "/ispsfl"}),
    "spk": frozenset({"/report", "/proverki"}),
}
# Даже при разрешённом кеше файлы, персональные запросы, опрос статуса и
# статистика не сохраняются автоматически.
_NO_CACHE_PATHS: dict[str, frozenset[str]] = {
    "fns": frozenset(
        {
            "/nalogbi_file",
            "/vyp",
            "/mspinfo_file",
            "/bo_file",
            "/innfl",
            "/mvdpass",
            "/mvdinfo",
            "/fl_status",
            "/zsk",
            "/stat",
        }
    ),
    "banks": frozenset({"/api/stat"}),
    "fssp": frozenset({"/ispfl", "/ispsfl"}),
    "spk": frozenset({"/report"}),
}
_SAFE_PATH = re.compile(r"/[A-Za-z0-9_/-]+\Z")
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class _QueryTransport(httpx.AsyncBaseTransport):
    """Добавить query после формирования безопасного запроса HTTPX."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport = transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        query = request.extensions.pop("damia_query")
        wire_request = httpx.Request(
            request.method,
            request.url.copy_merge_params(query),
            headers=request.headers,
            stream=request.stream,
            extensions=request.extensions,
        )
        return await self._transport.handle_async_request(wire_request)

    async def aclose(self) -> None:
        await self._transport.aclose()


@dataclass
class _Flight:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class HttpClient:
    """Переиспользуемый транспорт; повторы и кеш требуют отдельного разрешения.

    ``service`` определяет адрес и ключ из настроек; ``url`` — путь операции
    относительно этого адреса. Пока поддерживается только GET: расположение
    POST-параметров и ключа у поставщика не подтверждено.
    """

    def __init__(
        self,
        settings: DamiaSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        limits = httpx.Limits(max_connections=settings.max_connections)
        self._transport = _QueryTransport(
            transport
            if transport is not None
            else httpx.AsyncHTTPTransport(limits=limits, trust_env=False)
        )
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.timeout.connect,
                read=settings.timeout.read,
                write=settings.timeout.write,
                pool=settings.timeout.pool,
            ),
            limits=limits,
            follow_redirects=False,
            trust_env=False,
            transport=self._transport,
        )
        self._cache = ResponseCache(settings.cache)
        self._cache_secret = os.urandom(32)
        self._flights: dict[str, _Flight] = {}
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None
        self._http_closed = False

    async def request(
        self,
        method: str,
        url: str,
        *,
        service: ServiceName,
        params: Sequence[tuple[str, str]] | None = None,
        allow_retry: bool = False,
        allow_cache: bool = False,
        cache_validator: CacheValidator | None = None,
        cache_ttl: float | None = None,
    ) -> HttpResponse:
        """Отправить GET-запрос; необязательные политики включаются явно.

        Для кеша нужен ``cache_validator``: он подтверждает, что успешный HTTP-
        ответ допустимо сохранить. Без проверки нельзя исключить ошибку внутри
        2XX. Каждый получатель повторно проверяет общую запись своим валидатором;
        несовместимые проверки могут вызвать дополнительные запросы и замену.
        Single-flight не гарантирует один сетевой вызов. Нельзя передавать
        ключ в ``params`` или URL.
        """
        if self._closed:
            raise DamiaClientClosedError("HTTP-клиент закрыт.")
        if method.upper() != "GET":
            raise DamiaConfigurationError(
                "Поддерживаются только документированные GET-запросы."
            )
        full_url, key = self._prepare(service, url, params)
        permitted = url in _RETRY_PATHS[service]
        if allow_retry and not permitted:
            raise DamiaConfigurationError("Повтор для этой операции не разрешён.")
        if allow_cache and (
            not permitted or url in _NO_CACHE_PATHS.get(service, frozenset())
        ):
            raise DamiaConfigurationError("Кеширование для этой операции не разрешено.")
        if allow_cache and cache_validator is None:
            raise DamiaConfigurationError("Для кеширования нужна проверка результата.")
        if cache_ttl is not None and (
            not allow_cache or not math.isfinite(cache_ttl) or cache_ttl <= 0
        ):
            raise DamiaConfigurationError(
                "TTL кеша должен быть положительным и конечным."
            )

        query = [*(params or ()), ("key", key)]
        if not (allow_cache and self.settings.cache.enabled):
            return await self._perform(full_url, query, allow_retry=allow_retry)

        assert cache_validator is not None
        effective_ttl = self.settings.cache.ttl if cache_ttl is None else cache_ttl
        digest = self._cache_key(service, full_url, query, effective_ttl)
        flight = self._flights.setdefault(digest, _Flight())
        flight.users += 1
        try:
            async with flight.lock:
                if self._closed:
                    raise DamiaClientClosedError("HTTP-клиент закрыт.")
                cached = await self._cache.get(digest)
                if cached is not None and cache_validator(cached):
                    return cached
                generation = await self._cache.generation()
                if self._closed:
                    raise DamiaClientClosedError("HTTP-клиент закрыт.")
                response = await self._perform(full_url, query, allow_retry=allow_retry)
                content_type = (
                    (response.content_type or "").split(";", 1)[0].strip().lower()
                )
                if content_type == "application/json" and cache_validator(response):
                    await self._cache.set(
                        digest,
                        response,
                        ttl=effective_ttl,
                        generation=generation,
                        permitted=lambda: not self._closed,
                    )
                return response
        finally:
            flight.users -= 1
            if flight.users == 0:
                self._flights.pop(digest, None)

    def _prepare(
        self, service: ServiceName, path: str, params: Sequence[tuple[str, str]] | None
    ) -> tuple[str, str]:
        if service not in _RETRY_PATHS:
            raise DamiaConfigurationError("Неизвестный сервис API.")
        if (
            not _SAFE_PATH.fullmatch(path)
            or "//" in path
            or any(part in (".", "..") for part in path.split("/"))
        ):
            raise DamiaConfigurationError("Некорректный путь операции API.")
        if params and any(name.casefold() == "key" for name, _ in params):
            raise DamiaConfigurationError("API-ключ задаётся только через настройки.")
        base = getattr(self.settings.base_urls, service)
        try:
            parsed = urlsplit(base)
            _ = parsed.port
            httpx.URL(base)
        except (ValueError, httpx.InvalidURL):
            parsed = None
        if parsed is None:
            raise DamiaConfigurationError("Некорректный базовый адрес API.")
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(ord(character) <= 32 or ord(character) == 127 for character in base)
            or (parsed.path not in ("", "/") and not _SAFE_PATH.fullmatch(parsed.path))
            or "//" in parsed.path
            or any(part in (".", "..") for part in parsed.path.split("/"))
            or (
                parsed.scheme == "http"
                and parsed.hostname not in ("localhost", "127.0.0.1", "::1")
            )
        ):
            raise DamiaConfigurationError(
                "Некорректный или небезопасный базовый адрес API."
            )
        if service == "fns":
            secret = self.settings.fns_key
        elif service == "banks":
            secret = self.settings.banks_key
        else:
            service_secret = getattr(self.settings, f"{service}_key")
            secret = (
                service_secret
                if service_secret is not None
                else self.settings.damia_key
            )
        if secret is None or not secret.get_secret_value():
            raise DamiaConfigurationError(f"Не задан API-ключ для сервиса {service}.")
        key = secret.get_secret_value()
        try:
            key.encode("utf-8")
            for name, value in params or ():
                name.encode("utf-8")
                value.encode("utf-8")
        except UnicodeError:
            valid_utf8 = False
        else:
            valid_utf8 = True
        if not valid_utf8:
            raise DamiaConfigurationError(
                "Ключ или параметры содержат некорректные символы."
            )
        return base.rstrip("/") + path, key

    def _cache_key(
        self,
        service: ServiceName,
        url: str,
        query: Sequence[tuple[str, str]],
        ttl: float,
    ) -> str:
        payload = json.dumps(
            [service, url, list(query), ttl], ensure_ascii=False, separators=(",", ":")
        )
        return hmac.new(
            self._cache_secret, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    async def _perform(
        self, url: str, params: Sequence[tuple[str, str]], *, allow_retry: bool
    ) -> HttpResponse:
        if not (allow_retry and self.settings.retry.enabled):
            return await self._send_once(url, params)
        retry_settings = self.settings.retry
        wait_random = wait_random_exponential(
            multiplier=retry_settings.initial_delay, max=retry_settings.max_delay
        )

        def should_retry(exc: BaseException) -> bool:
            if isinstance(exc, DamiaHTTPError):
                return exc.status_code in _RETRYABLE_STATUSES and (
                    exc.retry_after is None
                    or exc.retry_after <= retry_settings.max_delay
                )
            return isinstance(exc, DamiaConnectionError)

        def wait(state: RetryCallState) -> float:
            delay = float(wait_random(state))
            exception = state.outcome.exception() if state.outcome is not None else None
            if (
                isinstance(exception, DamiaHTTPError)
                and exception.retry_after is not None
            ):
                delay = max(delay, exception.retry_after)
            return delay

        try:
            async with asyncio.timeout(retry_settings.max_elapsed):
                retrying = AsyncRetrying(
                    retry=retry_if_exception(should_retry),
                    stop=stop_after_attempt(retry_settings.max_attempts),
                    wait=wait,
                    reraise=True,
                )
                return await retrying(self._send_once, url, params)
        except TimeoutError:
            pass
        raise DamiaTimeoutError("Превышено общее время повторов API.")

    async def _send_once(
        self, url: str, params: Sequence[tuple[str, str]]
    ) -> HttpResponse:
        failure: DamiaError | None = None
        try:
            request = self._http.build_request(
                "GET", url, extensions={"damia_query": list(params)}
            )
            response = await self._http.send(request)
        except httpx.TimeoutException:
            failure = DamiaTimeoutError("Превышено время ожидания API.")
        except httpx.RequestError:
            failure = DamiaConnectionError("Не удалось выполнить запрос к API.")
        except (httpx.InvalidURL, UnicodeError):
            failure = DamiaConfigurationError("Некорректный адрес или параметры API.")
        if failure is not None:
            # Вне except исходное исключение HTTPX не попадает в __context__.
            raise failure
        if not 200 <= response.status_code < 300:
            retry_after = self._retry_after(response.headers.get("Retry-After"))
            if response.status_code == 429:
                raise DamiaRateLimitError(response.status_code, retry_after=retry_after)
            raise DamiaHTTPError(response.status_code, retry_after=retry_after)
        return HttpResponse(
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type"),
            body=response.content,
        )

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=UTC)
                seconds = (date - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                return None
        if not math.isfinite(seconds):
            if seconds == float("inf") and re.fullmatch(r"[0-9]+", value):
                return seconds
            return None
        return max(0.0, seconds)

    async def clear_cache(self) -> None:
        """Инвалидировать кеш до удаления; ошибки удаления можно повторить."""
        await self._cache.clear()

    async def _close_resources(self) -> None:
        failed = False
        try:
            try:
                await self._cache.close()
            except Exception:  # noqa: BLE001
                failed = True
        finally:
            if not self._http_closed:
                try:
                    if self._http.is_closed:
                        await self._transport.aclose()
                    else:
                        await self._http.aclose()
                except Exception:  # noqa: BLE001
                    failed = True
                else:
                    self._http_closed = True
        if failed:
            raise RuntimeError("Не удалось освободить ресурсы транспорта.")

    async def aclose(self) -> None:
        """Отклонить новые запросы и совместно ожидать освобождения ресурсов.

        Активные запросы могут завершиться ошибкой; после начала закрытия кеш
        не пополняется. Отмена ожидающего не отменяет общее закрытие. После
        ошибки повторный вызов повторяет незавершённое освобождение.
        """
        self._closed = True
        if self._close_task is None or (
            self._close_task.done()
            and not self._close_task.cancelled()
            and self._close_task.exception() is not None
        ):
            self._close_task = asyncio.create_task(self._close_resources())
            self._close_task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
        await asyncio.shield(self._close_task)

    async def __aenter__(self) -> Self:
        if self._closed:
            raise DamiaClientClosedError("HTTP-клиент закрыт.")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()
