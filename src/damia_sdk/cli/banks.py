"""Команды API-Банки."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.banks import BanksService

app = create_service_app(
    "banks",
    BanksService,
    (
        "bankdata",
        "bankinfo",
        "bankaraits",
        "bankbic",
        "bankotch",
        "banksrait",
        "listdata",
        "pokinfo",
        "stat",
    ),
    help_text="API-Банки. Запросы могут тарифицироваться.",
)
