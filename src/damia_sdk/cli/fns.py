"""Команды API-ФНС."""

from damia_sdk.cli.common import create_service_app
from damia_sdk.services.fns import FNSService

app = create_service_app(
    "fns",
    FNSService,
    (
        "search",
        "ac",
        "egr",
        "multinfo",
        "multcheck",
        "check",
        "nalogbi",
        "nalogbi_file",
        "changes",
        "mon",
        "vyp",
        "mspinfo_file",
        "bo",
        "bo_file",
        "innfl",
        "mvdpass",
        "mvdinfo",
        "fl_status",
        "fsrar",
        "zsk",
        "rom",
        "fias_info",
        "fias_search",
        "stat",
    ),
    help_text="API-ФНС. Запросы могут тарифицироваться. mon может менять мониторинг.",
)
