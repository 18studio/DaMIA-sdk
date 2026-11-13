"""Проверки структуры CLI без сетевых запросов."""

import inspect
import socket

import pytest
from typer.testing import CliRunner

from damia_sdk.cli import app
from damia_sdk.client import DamiaClient


@pytest.mark.parametrize(
    "group",
    ["fns", "rosstat", "banks", "scoring", "procurement", "arbitration", "fssp", "spk"],
)
def test_service_group_help(group: str) -> None:
    result = CliRunner().invoke(app, [group, "--help"])
    assert result.exit_code == 0
    assert group in result.stdout


def test_every_service_method_has_cli_help() -> None:
    client = DamiaClient()
    runner = CliRunner()
    count = 0
    for group in (
        "fns",
        "rosstat",
        "banks",
        "scoring",
        "procurement",
        "arbitration",
        "fssp",
        "spk",
    ):
        service = getattr(client, group)
        for name, _ in inspect.getmembers(service, inspect.iscoroutinefunction):
            if name.startswith("_"):
                continue
            command = name.replace("_", "-")
            result = runner.invoke(app, [group, command, "--help"])
            assert result.exit_code == 0, (group, name, result.output)
            count += 1
    assert count == 61


def test_command_help_does_not_call_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("CLI help must not use network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    result = CliRunner().invoke(app, ["fns", "egr", "--help"])
    assert result.exit_code == 0
    assert "--req" in result.stdout


def test_list_and_ambiguous_parameters_are_exposed() -> None:
    runner = CliRunner()
    repeated = runner.invoke(app, ["rosstat", "multbalance", "--help"])
    assert repeated.exit_code == 0
    assert "--inn-list" in repeated.stdout
    ambiguous = runner.invoke(app, ["arbitration", "dela", "--help"])
    assert ambiguous.exit_code == 0
    assert "--exact" in ambiguous.stdout


def test_invalid_option_has_usage_error() -> None:
    result = CliRunner().invoke(app, ["fns", "egr", "--not-a-real-option", "x"])
    assert result.exit_code == 2
