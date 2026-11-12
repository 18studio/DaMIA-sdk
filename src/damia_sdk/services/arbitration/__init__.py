"""Async skeleton for the arbitration API."""

from typing import NoReturn

from damia_sdk.transport.http import HttpClient


class ArbitrationService:
    """Arbitration endpoints; server-side parameter requirements are unconfirmed."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def delo(self, *, regn: str | None = None) -> NoReturn:
        """Get information about a case by its registration number."""
        raise NotImplementedError

    async def delopro(
        self, *, regn: str | None = None, a: str | None = None, email: str | None = None
    ) -> NoReturn:
        """Track a case or manage notifications.

        The first call for a case starts tracking; actions can change notifications.
        This GET can have side effects and is individually priced.
        """
        raise NotImplementedError

    async def dela(
        self,
        *,
        q: str | None = None,
        role: str | None = None,
        type: str | None = None,
        status: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        exact: object = None,
        format: int | None = None,
        page: int | None = None,
    ) -> NoReturn:
        """Get case participations; the type and serialization of exact are unknown."""
        raise NotImplementedError

    async def dsearch(
        self,
        *,
        type: str | None = None,
        status: str | None = None,
        court: str | None = None,
        min_summa: int | None = None,
        max_summa: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        page: int | None = None,
    ) -> NoReturn:
        """Search arbitration cases."""
        raise NotImplementedError
