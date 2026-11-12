"""HTTP transport skeleton."""

from types import TracebackType
from typing import NoReturn, Self

from damia_sdk.settings import DamiaSettings


class HttpClient:
    """Placeholder for the async HTTP transport."""

    def __init__(self, settings: DamiaSettings) -> None:
        self.settings = settings

    async def request(self) -> NoReturn:
        raise NotImplementedError

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        pass
