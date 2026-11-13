"""SPK and inspections API."""

from damia_sdk.transport.http import HttpClient
from damia_sdk.transport.response import HttpResponse


class SpkService:
    """SPK reports and prosecutor inspections."""

    def __init__(self, transport: HttpClient) -> None:
        self._transport = transport

    async def report(
        self,
        *,
        req: str | None = None,
        format: str | None = None,
        sections: str | None = None,
    ) -> HttpResponse:
        """Get a comprehensive counterparty report."""
        params = [
            (name, value)
            for name, value in (
                ("req", req),
                ("format", format),
                ("sections", sections),
            )
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/report", service="spk", params=params
        )

    async def proverki(
        self,
        *,
        req: str | None = None,
        status: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        page: int | None = None,
    ) -> HttpResponse:
        """Get prosecutor inspections."""
        params = [
            (name, value)
            for name, value in (
                ("req", req),
                ("status", status),
                ("from_date", from_date),
                ("to_date", to_date),
                ("page", str(page) if page is not None else None),
            )
            if value is not None
        ]
        return await self._transport.request(
            "GET", "/proverki", service="spk", params=params
        )
