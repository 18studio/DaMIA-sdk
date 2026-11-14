"""Проверки структуры CLI без сетевых запросов."""

import inspect
import socket

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from damia_sdk.cli import (
    app,
    arbitration,
    banks,
    fns,
    fssp,
    procurement,
    rosstat,
    scoring,
    spk,
)
from damia_sdk.client import DamiaClient
from damia_sdk.services.arbitration import ArbitrationService
from damia_sdk.services.banks import BanksService
from damia_sdk.services.fns import FNSService
from damia_sdk.services.fssp import FsspService
from damia_sdk.services.procurement import ProcurementService
from damia_sdk.services.rosstat import RosstatService
from damia_sdk.services.scoring import ScoringService
from damia_sdk.services.spk import SpkService


@pytest.mark.parametrize(
    "group",
    ["fns", "rosstat", "banks", "scoring", "procurement", "arbitration", "fssp", "spk"],
)
def test_service_group_help(group: str) -> None:
    result = CliRunner().invoke(app, [group, "--help"])
    assert result.exit_code == 0
    assert group in result.stdout


def test_every_service_method_has_cli_help(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("help must not create client or use network")

    monkeypatch.setattr(DamiaClient, "__init__", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    runner = CliRunner()
    count = 0
    for group, module, service in (
        ("fns", fns, FNSService),
        ("rosstat", rosstat, RosstatService),
        ("banks", banks, BanksService),
        ("scoring", scoring, ScoringService),
        ("procurement", procurement, ProcurementService),
        ("arbitration", arbitration, ArbitrationService),
        ("fssp", fssp, FsspService),
        ("spk", spk, SpkService),
    ):
        methods = {
            name: method
            for name, method in inspect.getmembers(service, inspect.iscoroutinefunction)
            if not name.startswith("_")
        }
        group_command = get_command(module.app)
        commands = getattr(group_command, "commands")  # noqa: B009
        assert set(commands) == {name.replace("_", "-") for name in methods}
        for name, method in methods.items():
            result = runner.invoke(app, [group, name.replace("_", "-"), "--help"])
            assert result.exit_code == 0, (group, name, result.output)
            for parameter in inspect.signature(method).parameters.values():
                if parameter.name == "self":
                    continue
                option = (
                    "--balance-field"
                    if parameter.name == "balance_fields"
                    else "--" + parameter.name.replace("_", "-")
                )
                assert option in result.stdout, (group, name, option)
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


@pytest.mark.parametrize("args", [["--help"], ["version-info"]])
def test_root_help_and_version_without_client_or_network(
    monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("client or network")

    monkeypatch.setattr(DamiaClient, "__init__", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    assert CliRunner().invoke(app, args).exit_code == 0
