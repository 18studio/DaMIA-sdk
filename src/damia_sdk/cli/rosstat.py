"""Заготовки команд API-Росстат."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.rosstat import RosstatService

app = create_service_app(
    "rosstat",
    RosstatService,
    ("balance", "multbalance", "statcodes"),
    help_text="API-Росстат. Команды пока не выполняют запросы.",
)
