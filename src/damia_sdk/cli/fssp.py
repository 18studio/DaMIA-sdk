"""Команды API-ФССП."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.fssp import FsspService

app = create_service_app(
    "fssp",
    FsspService,
    ("isp", "isps", "ispfl", "ispsfl"),
    help_text="API-ФССП. Запросы могут тарифицироваться.",
)
