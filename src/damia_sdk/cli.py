"""Точка входа CLI DaMIA SDK."""

from importlib.metadata import version

import typer

app = typer.Typer(help="Командная строка DaMIA SDK.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Команды DaMIA SDK."""


@app.command()
def version_info() -> None:
    """Показать версию установленного SDK."""
    typer.echo(version("damia-sdk"))
