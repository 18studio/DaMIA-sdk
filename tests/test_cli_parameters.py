"""Проверки контракта параметров CLI без SDK-запросов."""

import socket
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from damia_sdk.cli import app
from damia_sdk.cli.common import convert_parameters
from damia_sdk.client import DamiaClient
from damia_sdk.services.arbitration import ArbitrationService
from damia_sdk.services.fns import FNSService
from damia_sdk.services.procurement import ProcurementService
from damia_sdk.services.rosstat import RosstatService
from damia_sdk.services.scoring import ScoringService
from damia_sdk.settings import DamiaSettings


@pytest.fixture(autouse=True)
def no_network_or_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network or client creation")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(DamiaClient, "__init__", forbidden)


@pytest.mark.parametrize(
    ("method", "scalar", "list_name"),
    [
        (FNSService.multinfo, "req", "req_list"),
        (FNSService.multcheck, "req", "req_list"),
        (RosstatService.multbalance, "inn", "inn_list"),
    ],
)
def test_lists(method: Callable[..., Any], scalar: str, list_name: str) -> None:
    assert convert_parameters(method, {scalar: None, list_name: []})[list_name] is None
    values = {scalar: "001", list_name: ["002", "001", "002"]}
    assert convert_parameters(method, values) == values


def test_integers_and_objects() -> None:
    assert convert_parameters(
        ProcurementService.zakupka, {"regn": "0001", "actual": "0"}
    ) == {"regn": "0001", "actual": 0}
    assert convert_parameters(ProcurementService.zakupka, {"actual": None}) == {
        "actual": None
    }
    assert convert_parameters(ProcurementService.zakupka, {"actual": "-3"}) == {
        "actual": -3
    }
    assert convert_parameters(ArbitrationService.dela, {"exact": "false"}) == {
        "exact": "false"
    }
    assert convert_parameters(ProcurementService.zfas, {"format": None}) == {
        "format": None
    }
    assert convert_parameters(ProcurementService.zfas, {"format": "001"}) == {
        "format": "001"
    }


def test_mapping() -> None:
    method = ScoringService.score
    assert convert_parameters(method, {"balance_fields": []}) == {
        "balance_fields": None
    }
    assert convert_parameters(method, {"balance_fields": ["x=-1", "other=0"]}) == {
        "balance_fields": {"x": -1, "other": 0}
    }
    for values in (["=1"], ["x=1", "x=2"], ["x=secret"], ["secret"]):
        with pytest.raises(ValueError) as error:
            convert_parameters(method, {"balance_fields": values})
        assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "args",
    [
        ["procurement", "zakupka", "--actual", "sensitive-value"],
        ["scoring", "score", "--balance-field", "sensitive-value=bad"],
        [
            "scoring",
            "score",
            "--balance-field",
            "sensitive-value=1",
            "--balance-field",
            "sensitive-value=2",
        ],
    ],
)
def test_errors_hide_values(args: list[str]) -> None:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "sensitive-value" not in result.output


def test_valid_command_hides_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from damia_sdk.cli import common
    from damia_sdk.transport.response import HttpResponse

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        @property
        def fns(self) -> Any:
            return self

        async def multinfo(self, **kwargs: Any) -> HttpResponse:
            assert kwargs["req"] == "sensitive-value"
            assert kwargs["req_list"] == ["sensitive-value"]
            return HttpResponse(200, "application/json", b"null")

    monkeypatch.setattr(common, "DamiaClient", Client)
    monkeypatch.setattr(DamiaSettings, "from_env", lambda: None)
    result = CliRunner().invoke(
        app,
        [
            "fns",
            "multinfo",
            "--req",
            "sensitive-value",
            "--req-list",
            "sensitive-value",
        ],
    )
    assert result.exit_code == 0
    assert "sensitive-value" not in result.output


@pytest.mark.parametrize(
    ("group", "command", "scalar", "list_option", "list_name"),
    [
        ("fns", "multinfo", "req", "req-list", "req_list"),
        ("fns", "multcheck", "req", "req-list", "req_list"),
        ("rosstat", "multbalance", "inn", "inn-list", "inn_list"),
    ],
)
def test_cli_list_parsing(
    monkeypatch: pytest.MonkeyPatch,
    group: str,
    command: str,
    scalar: str,
    list_option: str,
    list_name: str,
) -> None:
    from damia_sdk.cli import common

    captured: list[dict[str, Any]] = []
    convert = common.convert_parameters

    def capture(
        method: Callable[..., Any], values: Mapping[str, Any]
    ) -> dict[str, Any]:
        result = convert(method, values)
        captured.append(result)
        return result

    monkeypatch.setattr(common, "convert_parameters", capture)
    runner = CliRunner()
    assert runner.invoke(app, [group, command]).exit_code == 1
    assert captured[-1][list_name] is None
    args = [group, command, f"--{scalar}", "001"]
    for value in ("002", "001", "002"):
        args.extend([f"--{list_option}", value])
    assert runner.invoke(app, args).exit_code == 1
    assert captured[-1][scalar] == "001"
    assert captured[-1][list_name] == ["002", "001", "002"]


@pytest.mark.parametrize(
    "args",
    [
        ["secret-value"],
        ["--secret-value"],
        ["fns", "secret-value"],
        ["fns", "--secret-value"],
        ["fns", "egr", "--secret-value"],
        ["fns", "egr", "--req"],
        ["procurement", "zakupka", "--actual", "secret-value"],
        ["scoring", "score", "--balance-field", "secret-value=bad"],
    ],
)
def test_parameter_errors_are_masked_at_every_level(args: list[str]) -> None:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "Ошибка параметров." in result.stderr
    assert "secret-value" not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("source", ["file", "stdin"])
@pytest.mark.parametrize(
    ("command", "content", "extra"),
    [
        ("egr", b"\xffsecret-value", []),
        ("egr", b'["secret-value"]', []),
        ("egr", b'"secret-value"', []),
        ("egr", b"null", []),
        ("egr", b'{"req":"secret-value"', []),
        ("egr", b'{"req":"secret-value","req":"x"}', []),
        ("egr", b'{"secret-value":"x"}', []),
        ("egr", b'{"req":123}', []),
        ("egr", b'{"req":NaN}', []),
        ("egr", b'{"req":Infinity}', []),
        ("egr", b'{"req":-Infinity}', []),
        ("egr", b'{"req":"secret-value"}', ["--req", "secret-value"]),
        ("multinfo", b'{"req_list":["secret-value",1]}', []),
    ],
)
def test_params_file_invalid_input_is_masked(
    tmp_path: Path, source: str, command: str, content: bytes, extra: list[str]
) -> None:
    path = tmp_path / "secret-value"
    path.write_bytes(content)
    result = CliRunner().invoke(
        app,
        ["fns", command, "--params-file", str(path) if source == "file" else "-"]
        + extra,
        input=content if source == "stdin" else None,
    )
    assert result.exit_code == 2
    assert "Ошибка параметров." in result.stderr
    assert "secret-value" not in result.output
    assert "Traceback" not in result.output


def test_missing_params_file_is_masked(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["fns", "egr", "--params-file", str(tmp_path / "secret-value")]
    )
    assert result.exit_code == 2
    assert "Ошибка параметров." in result.stderr
    assert "secret-value" not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("source", ["file", "stdin"])
def test_deep_params_are_masked_before_client(tmp_path: Path, source: str) -> None:
    depth = sys.getrecursionlimit() + 100
    content = '{"req":' + "[" * depth + '"secret-value"' + "]" * depth + "}"
    path = tmp_path / "secret-value"
    path.write_text(content, encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["fns", "egr", "--params-file", str(path) if source == "file" else "-"],
        input=content if source == "stdin" else None,
    )
    assert result.exit_code == 2
    assert "Ошибка параметров." in result.stderr
    assert "secret-value" not in result.output and "Traceback" not in result.output
