"""Async arbitration API operations."""

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


def _params(**values: object) -> list[tuple[str, str]]:
    return [(name, str(value)) for name, value in values.items() if value is not None]


class ArbitrationService:
    """Arbitration endpoints; server-side parameter requirements are unconfirmed."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def delo(self, *, regn: str | None = None) -> HttpResponse:
        """Get information about a case by its registration number."""
        return await self._transport.request(
            "GET", "/arb/delo", service="arbitration", params=_params(regn=regn)
        )

    async def delopro(
        self, *, regn: str | None = None, a: str | None = None, email: str | None = None
    ) -> HttpResponse:
        """Track a case or manage notifications.

        The first call for a case starts tracking; actions can change notifications.
        This GET can have side effects and is individually priced.
        """
        return await self._transport.request(
            "GET",
            "/arb/delopro",
            service="arbitration",
            params=_params(regn=regn, a=a, email=email),
        )

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
    ) -> HttpResponse:
        """Get case participations.

        The wire encoding of exact is unconfirmed; supplied values are stringified.
        """
        return await self._transport.request(
            "GET",
            "/arb/dela",
            service="arbitration",
            params=_params(
                q=q,
                role=role,
                type=type,
                status=status,
                from_date=from_date,
                to_date=to_date,
                exact=exact,
                format=format,
                page=page,
            ),
        )

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
    ) -> HttpResponse:
        """Search arbitration cases."""
        return await self._transport.request(
            "GET",
            "/arb/dsearch",
            service="arbitration",
            params=_params(
                type=type,
                status=status,
                court=court,
                min_summa=min_summa,
                max_summa=max_summa,
                from_date=from_date,
                to_date=to_date,
                page=page,
            ),
        )
