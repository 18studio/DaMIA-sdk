"""Команды API-Арбитражи."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.arbitration import ArbitrationService

app = create_service_app(
    "arbitration",
    ArbitrationService,
    ("delo", "delopro", "dela", "dsearch"),
    help_text="API-Арбитражи. Запросы могут тарифицироваться. delopro может включить отслеживание.",
)
