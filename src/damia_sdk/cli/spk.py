"""Заготовки команд API-СПК и проверок."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.spk import SpkService

app = create_service_app(
    "spk",
    SpkService,
    ("report", "proverki"),
    help_text="API-СПК и проверки. Команды пока не выполняют запросы.",
)
