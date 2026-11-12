"""Проверки базового CLI."""

from typer.testing import CliRunner

from damia_sdk.cli import app


def test_version_info() -> None:
    result = CliRunner().invoke(app, ["version-info"])
    assert result.exit_code == 0
    assert result.stdout.strip()
