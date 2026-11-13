"""Точка входа CLI DaMIA SDK."""

from importlib.metadata import version

import typer

from damia_sdk.cli import (
    arbitration,
    banks,
    fns,
    fssp,
    procurement,
    rosstat,
    scoring,
    spk,
)

app = typer.Typer(
    help="Командная строка DaMIA SDK. Команды API пока не реализованы.",
    no_args_is_help=True,
)

app.add_typer(fns.app, name="fns")
app.add_typer(rosstat.app, name="rosstat")
app.add_typer(banks.app, name="banks")
app.add_typer(scoring.app, name="scoring")
app.add_typer(procurement.app, name="procurement")
app.add_typer(arbitration.app, name="arbitration")
app.add_typer(fssp.app, name="fssp")
app.add_typer(spk.app, name="spk")


@app.callback()
def main() -> None:
    """Команды DaMIA SDK."""


@app.command()
def version_info() -> None:
    """Показать версию установленного SDK."""
    typer.echo(version("damia-sdk"))
