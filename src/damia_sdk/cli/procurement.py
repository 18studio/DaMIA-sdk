"""Заготовки команд API-Закупки."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.procurement import ProcurementService

app = create_service_app(
    "procurement",
    ProcurementService,
    (
        "zakupka",
        "contract",
        "zakupki",
        "contracts",
        "zsearch",
        "customer",
        "eruz",
        "zfas",
        "rnp",
        "sro",
        "ktru",
        "zmon",
    ),
    help_text="API-Закупки. Команды пока не выполняют запросы. zmon может менять подписки.",
)
