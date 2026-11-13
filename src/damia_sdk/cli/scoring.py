"""Заготовки команд API-Скоринг."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.scoring import ScoringService

app = create_service_app(
    "scoring",
    ScoringService,
    ("score", "info", "fincoefs"),
    help_text="API-Скоринг. Команды пока не выполняют запросы.",
)
