"""Асинхронная точка входа SDK без реализации сетевых запросов."""

from types import TracebackType
from typing import Self

from damia_sdk.services.arbitration import ArbitrationService
from damia_sdk.services.banks import BanksService
from damia_sdk.services.fns import FNSService
from damia_sdk.services.fssp import FsspService
from damia_sdk.services.procurement import ProcurementService
from damia_sdk.services.rosstat import RosstatService
from damia_sdk.services.scoring import ScoringService
from damia_sdk.services.spk import SpkService
from damia_sdk.settings import DamiaSettings
from damia_sdk.transport.http import HttpClient


class DamiaClient:
    """Группирует сервисы и предоставляет им общие настройки и транспорт.

    Этот класс — скелет: методы сервисов и сетевые запросы пока не реализованы.
    Переменные окружения автоматически не читаются; для этого нужно явно
    вызвать ``DamiaSettings.from_env()``.
    """

    def __init__(self, *, settings: DamiaSettings | None = None) -> None:
        self.settings = settings if settings is not None else DamiaSettings()
        self._transport = HttpClient(self.settings)
        self.fns = FNSService(self._transport)
        self.rosstat = RosstatService(self._transport)
        self.banks = BanksService(self._transport)
        self.scoring = ScoringService(self._transport)
        self.procurement = ProcurementService(self._transport)
        self.arbitration = ArbitrationService(self._transport)
        self.fssp = FsspService(self._transport)
        self.spk = SpkService(self._transport)

    async def __aenter__(self) -> Self:
        await self._transport.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._transport.__aexit__(exc_type, exc_value, traceback)
