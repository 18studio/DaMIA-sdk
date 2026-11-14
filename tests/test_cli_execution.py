"""CLI execution tests use only synthetic responses and a fake SDK client."""

import json
import os
import socket
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self

import pytest
from typer.testing import CliRunner

from damia_sdk.cli import app, common
from damia_sdk.settings import DamiaSettings
from damia_sdk.transport.response import HttpResponse

EXPECTED_FILE_METHODS = frozenset({"nalogbi_file", "vyp", "mspinfo_file", "bo_file"})


def test_file_methods_match_expected_inventory() -> None:
    assert common.FILE_METHODS == EXPECTED_FILE_METHODS


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def fake_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[Any], Callable[[HttpResponse], None]]:
    calls: list[Any] = []
    response = HttpResponse(200, "application/json", b'"ok"')

    class Client:
        def __init__(self, *, settings: Any) -> None:
            calls.append(("settings", settings))

        async def __aenter__(self) -> Self:
            calls.append("enter")
            return self

        async def __aexit__(self, *args: object) -> None:
            calls.append("exit")

        def __getattr__(self, service: str) -> SimpleNamespace:
            async def invoke(**params: Any) -> HttpResponse:
                calls.append((service, params))
                return response

            return SimpleNamespace(egr=invoke, vyp=invoke)

    monkeypatch.setattr(common, "DamiaClient", Client)
    monkeypatch.setattr(DamiaSettings, "from_env", lambda: "settings")

    def response_set(value: HttpResponse) -> None:
        nonlocal response
        response = value

    return calls, response_set


def test_json_and_context(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]],
) -> None:
    calls, _ = fake_client
    result = CliRunner().invoke(app, ["fns", "egr", "--req", "001"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == "ok"
    assert calls[0] == ("settings", "settings")
    assert calls[1] == "enter" and calls[-1] == "exit"
    assert calls[2][0] == "fns" and calls[2][1]["req"] == "001"


def test_file_output(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]], tmp_path: Path
) -> None:
    _, set_response = fake_client
    set_response(HttpResponse(200, "application/octet-stream", b"\x00\xff"))
    path = tmp_path / "output"
    result = CliRunner().invoke(app, ["fns", "vyp", "--output", str(path)])
    assert result.exit_code == 0 and result.stdout == ""
    assert path.read_bytes() == b"\x00\xff"
    if os.name == "posix":
        assert path.stat().st_mode & 0o177 == 0
    assert CliRunner().invoke(app, ["fns", "vyp", "--output", str(path)]).exit_code == 1


def test_params_file_and_conflict(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]], tmp_path: Path
) -> None:
    calls, _ = fake_client
    path = tmp_path / "params"
    path.write_text('{"req":"001"}', encoding="utf-8")
    result = CliRunner().invoke(app, ["fns", "egr", "--params-file", str(path)])
    assert result.exit_code == 0 and calls[2][1]["req"] == "001"
    result = CliRunner().invoke(
        app, ["fns", "egr", "--params-file", str(path), "--req", "secret"]
    )
    assert result.exit_code == 2 and "secret" not in result.output


def test_parse_errors_hide_input() -> None:
    for args in [
        ["secret-value"],
        ["fns", "egr", "--secret-value"],
        ["fns", "egr", "secret-value"],
    ]:
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 2 and "secret-value" not in result.output


def test_every_command_calls_matching_sdk_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from typer.main import get_command

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

    calls: list[tuple[str, str, dict[str, Any]]] = []

    class Service:
        def __init__(self, name: str) -> None:
            self.name = name

        def __getattr__(self, method: str) -> Callable[..., Any]:
            async def invoke(**kwargs: Any) -> HttpResponse:
                calls.append((self.name, method, kwargs))
                return HttpResponse(200, "application/json", b"null")

            return invoke

    class Client:
        def __init__(self, *, settings: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def __getattr__(self, name: str) -> Service:
            return Service(name)

    monkeypatch.setattr(common, "DamiaClient", Client)
    monkeypatch.setattr(DamiaSettings, "from_env", lambda: None)
    for name, module in [
        ("fns", fns),
        ("rosstat", rosstat),
        ("banks", banks),
        ("scoring", scoring),
        ("procurement", procurement),
        ("arbitration", arbitration),
        ("fssp", fssp),
        ("spk", spk),
    ]:
        for command in getattr(get_command(module.app), "commands"):  # noqa: B009
            args = [name, command]
            if name == "fns" and command.replace("-", "_") in EXPECTED_FILE_METHODS:
                args += ["--output", str(tmp_path / command)]
            result = CliRunner().invoke(app, args)
            assert result.exit_code == 0, (args, result.output)
            assert calls[-1][:2] == (name, command.replace("-", "_"))
            assert "output" not in calls[-1][2]
    assert len(calls) == 61


def test_terminal_and_redirect_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    common._render(HttpResponse(200, "text/plain", b"\x1b]0;x\x07\r\n\t\x7f"), None)
    assert capsys.readouterr().out == r"\u001b]0;x\u0007\u000d" + "\n\t" + r"\u007f"
    common._render(
        HttpResponse(
            200, "application/problem+json; charset=utf-8", b'"\\u001b\\u007f\\u009b"'
        ),
        None,
    )
    output = capsys.readouterr().out
    assert json.loads(output) == "\x1b\x7f\x9b"
    assert not any(c in output for c in "\x1b\x7f\x9b")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    common._render(HttpResponse(200, "text/plain", b"\x1b\r"), None)
    assert capsys.readouterr().out == "\x1b\r"


def test_file_symlink_and_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"original")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(FileExistsError):
        common._write_output(str(link), b"new")
    assert target.read_bytes() == b"original"

    path = tmp_path / "partial"
    original_fdopen = os.fdopen

    class PartialWriter:
        def __init__(self, fd: int) -> None:
            self.stream = original_fdopen(fd, "wb")

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            self.stream.close()

        def write(self, data: bytes) -> None:
            self.stream.write(data[:1])
            raise OSError("secret error")

    monkeypatch.setattr(os, "fdopen", lambda fd, mode: PartialWriter(fd))
    with pytest.raises(OSError):
        common._write_output(str(path), b"partial")
    assert not path.exists()


def test_deep_params_file_rejected_before_client(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]], tmp_path: Path
) -> None:
    import sys

    calls, _ = fake_client
    path = tmp_path / "deep.json"
    depth = sys.getrecursionlimit() + 100
    path.write_text(
        '{"req":' + "[" * depth + '"secret"' + "]" * depth + "}", encoding="utf-8"
    )
    result = CliRunner().invoke(app, ["fns", "egr", "--params-file", str(path)])
    assert result.exit_code == 2
    assert "Ошибка параметров." in result.output
    assert "Traceback" not in result.output and "secret" not in result.output
    assert calls == []


def test_client_context_closes_on_sdk_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Client:
        def __init__(self, *, settings: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            calls.append("enter")
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            assert exc_type is RuntimeError
            calls.append("exit")

        @property
        def fns(self) -> Self:
            return self

        async def egr(self, **kwargs: Any) -> HttpResponse:
            raise RuntimeError("secret")

    monkeypatch.setattr(common, "DamiaClient", Client)
    monkeypatch.setattr(DamiaSettings, "from_env", lambda: None)
    result = CliRunner().invoke(app, ["fns", "egr", "--req", "001"])
    assert result.exit_code == 1
    assert "secret" not in result.output and "Traceback" not in result.output
    assert calls == ["enter", "exit"]


def _command_cases() -> list[tuple[str, str, Any]]:
    from typer.main import get_command

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
    from damia_sdk.services.arbitration import ArbitrationService
    from damia_sdk.services.banks import BanksService
    from damia_sdk.services.fns import FNSService
    from damia_sdk.services.fssp import FsspService
    from damia_sdk.services.procurement import ProcurementService
    from damia_sdk.services.rosstat import RosstatService
    from damia_sdk.services.scoring import ScoringService
    from damia_sdk.services.spk import SpkService

    services = [
        ("fns", fns, FNSService),
        ("rosstat", rosstat, RosstatService),
        ("banks", banks, BanksService),
        ("scoring", scoring, ScoringService),
        ("procurement", procurement, ProcurementService),
        ("arbitration", arbitration, ArbitrationService),
        ("fssp", fssp, FsspService),
        ("spk", spk, SpkService),
    ]
    cases = [
        (name, command, getattr(cls, command.replace("-", "_")))
        for name, module, cls in services
        for command in getattr(get_command(module.app), "commands")  # noqa: B009
    ]
    assert len(cases) == 61
    return cases


@pytest.mark.parametrize(("service", "command", "method"), _command_cases())
def test_every_command_forwards_all_parameters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    service: str,
    command: str,
    method: Any,
) -> None:
    import inspect
    from collections.abc import Mapping
    from typing import get_args, get_origin, get_type_hints

    calls: list[tuple[str, str, dict[str, Any]]] = []

    class Service:
        def __getattr__(self, name: str) -> Any:
            async def invoke(**kwargs: Any) -> HttpResponse:
                calls.append((service, name, kwargs))
                return HttpResponse(200, "application/json", b"null")

            return invoke

    class Client:
        def __init__(self, *, settings: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        def __getattr__(self, name: str) -> Service:
            assert name == service
            return Service()

    monkeypatch.setattr(common, "DamiaClient", Client)
    monkeypatch.setattr(DamiaSettings, "from_env", lambda: None)
    args = [service, command]
    expected: dict[str, Any] = {}
    hints = get_type_hints(method)
    for name in inspect.signature(method).parameters:
        if name == "self":
            continue
        hint = hints[name]
        parts = get_args(hint)
        option = "--" + name.replace("_", "-")
        if any(get_origin(part) is Mapping for part in parts):
            args += ["--balance-field", "x=-2", "--balance-field", "y=0"]
            expected[name] = {"x": -2, "y": 0}
        elif any(get_origin(part) is list for part in parts):
            args += [option, "001", option, "002"]
            expected[name] = ["001", "002"]
        elif hint is int or int in parts:
            args += [option, "-3"]
            expected[name] = -3
        else:
            args += [option, "001"]
            expected[name] = "001"
    if service == "fns" and command.replace("-", "_") in EXPECTED_FILE_METHODS:
        args += ["--output", str(tmp_path / "result")]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert calls == [(service, command.replace("-", "_"), expected)]


@pytest.mark.parametrize(
    ("mime", "body", "code", "stdout"),
    [
        (
            " Application/JSON ; charset=UTF-8",
            '"привет"'.encode(),
            0,
            '"\\u043f\\u0440\\u0438\\u0432\\u0435\\u0442"\n',
        ),
        ("Application/Problem+JSON; charset=utf-8", b'{"x":1}', 0, '{"x": 1}\n'),
        ("TEXT/PLAIN; charset=ascii", b"a\xffb", 0, "a\ufffdb"),
        (None, b"secret-body", 1, ""),
        ("application/json", b'{"secret-body":', 1, ""),
        ("application/json", b"NaN", 1, ""),
        ("application/octet-stream", b"\x00secret-body\xff", 1, ""),
    ],
)
def test_response_mime_and_safe_errors(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]],
    mime: str | None,
    body: bytes,
    code: int,
    stdout: str,
) -> None:
    _, set_response = fake_client
    set_response(HttpResponse(200, mime, body))
    result = CliRunner().invoke(app, ["fns", "egr"])
    assert result.exit_code == code
    assert result.stdout == stdout
    assert result.stderr == ("Ошибка выполнения команды.\n" if code else "")
    assert "secret-body" not in result.stderr


@pytest.mark.parametrize("failure", ["fstat", "fdopen", "write", "close", "replaced"])
def test_output_failure_descriptor_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    path = tmp_path / "output"
    displaced = tmp_path / "displaced"
    real_open, real_fstat, real_fdopen = os.open, os.fstat, os.fdopen
    descriptors: list[int] = []

    def tracked_open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        descriptors.append(fd)
        return fd

    def broken_fstat(fd: int) -> os.stat_result:
        raise OSError("secret")

    class BrokenStream:
        def __init__(self, fd: int) -> None:
            self.stream = real_fdopen(fd, "wb")

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            self.stream.close()
            if failure == "close":
                raise OSError("secret")

        def write(self, data: bytes) -> None:
            self.stream.write(data[:1])
            if failure == "replaced":
                path.rename(displaced)
                path.write_bytes(b"replacement")
            if failure != "close":
                raise OSError("secret")

    def broken_fdopen(fd: int, mode: str) -> Any:
        if failure == "fdopen":
            raise OSError("secret")
        return BrokenStream(fd)

    monkeypatch.setattr(os, "open", tracked_open)
    if failure == "fstat":
        monkeypatch.setattr(os, "fstat", broken_fstat)
    else:
        monkeypatch.setattr(os, "fdopen", broken_fdopen)
    with pytest.raises(OSError):
        common._write_output(str(path), b"body")
    monkeypatch.setattr(os, "fstat", real_fstat)
    monkeypatch.setattr(os, "open", real_open)
    monkeypatch.setattr(os, "fdopen", real_fdopen)
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        real_fstat(descriptors[0])
    if failure == "fstat":
        assert path.read_bytes() == b""
    elif failure == "replaced":
        assert path.read_bytes() == b"replacement"
        assert displaced.read_bytes() == b"b"
    else:
        assert not path.exists()


def test_file_error_hides_path_and_body(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]], tmp_path: Path
) -> None:
    _, set_response = fake_client
    set_response(HttpResponse(200, "text/plain", b"secret-body"))
    path = tmp_path / "secret-path"
    path.write_bytes(b"original")
    result = CliRunner().invoke(app, ["fns", "vyp", "--output", str(path)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Ошибка выполнения команды.\n"
    assert path.read_bytes() == b"original"


@pytest.mark.parametrize(
    "stage", ["settings", "create", "enter", "method", "exit", "render"]
)
def test_execution_errors_are_masked(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    def fail() -> None:
        raise RuntimeError("secret-value")

    class Client:
        def __init__(self, *, settings: Any) -> None:
            if stage == "create":
                fail()

        async def __aenter__(self) -> Self:
            if stage == "enter":
                fail()
            return self

        async def __aexit__(self, *args: object) -> None:
            if stage == "exit":
                fail()

        @property
        def fns(self) -> Self:
            return self

        async def egr(self, **kwargs: Any) -> HttpResponse:
            if stage == "method":
                fail()
            return HttpResponse(200, "application/json", b"null")

    def settings() -> None:
        if stage == "settings":
            fail()

    def render(response: HttpResponse, output: str | None) -> None:
        fail()

    monkeypatch.setattr(common, "DamiaClient", Client)
    monkeypatch.setattr(DamiaSettings, "from_env", settings)
    if stage == "render":
        monkeypatch.setattr(common, "_render", render)
    result = CliRunner().invoke(app, ["fns", "egr"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Ошибка выполнения команды.\n"
    assert "secret-value" not in result.output and "Traceback" not in result.output


@pytest.mark.parametrize(
    "error_name",
    [
        "DamiaError",
        "DamiaConfigurationError",
        "DamiaClientClosedError",
        "DamiaConnectionError",
        "DamiaTimeoutError",
        "DamiaHTTPError",
        "DamiaRateLimitError",
        "DamiaResponseError",
    ],
)
def test_public_sdk_errors_are_masked(
    monkeypatch: pytest.MonkeyPatch, error_name: str
) -> None:
    from damia_sdk import exceptions

    error_type = getattr(exceptions, error_name)
    error = (
        error_type(429)
        if issubclass(error_type, exceptions.DamiaHTTPError)
        else error_type("secret-value")
    )

    def fail() -> None:
        raise error

    monkeypatch.setattr(DamiaSettings, "from_env", fail)
    result = CliRunner().invoke(app, ["fns", "egr"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Ошибка выполнения команды.\n"
    assert str(error) not in result.output and "Traceback" not in result.output


@pytest.mark.parametrize("command", sorted(EXPECTED_FILE_METHODS))
def test_all_file_methods_require_output_and_preserve_bytes(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    command: str,
) -> None:
    calls, set_response = fake_client
    set_response(HttpResponse(200, "application/octet-stream", b"\x00\xff"))
    missing = CliRunner().invoke(app, ["fns", command.replace("_", "-")])
    assert missing.exit_code == 2 and calls == []
    path = tmp_path / "secret-path"

    # Existing fake exposes only two methods; provide the remaining synthetic methods.
    class Service:
        def __getattr__(self, name: str) -> Any:
            async def invoke(**kwargs: Any) -> HttpResponse:
                return HttpResponse(200, "application/octet-stream", b"\x00\xff")

            return invoke

    class Client:
        def __init__(self, *, settings: Any) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        @property
        def fns(self) -> Service:
            return Service()

    monkeypatch.setattr(common, "DamiaClient", Client)
    args = ["fns", command.replace("_", "-"), "--output", str(path)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0 and result.stdout == ""
    assert path.read_bytes() == b"\x00\xff"
    if os.name == "posix":
        assert path.stat().st_mode & 0o177 == 0
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1 and result.stdout == ""
    assert result.stderr == "Ошибка выполнения команды.\n"
    assert path.read_bytes() == b"\x00\xff"


@pytest.mark.parametrize("source", ["file", "stdin"])
def test_params_utf8_preserves_values(
    fake_client: tuple[list[Any], Callable[[HttpResponse], None]],
    tmp_path: Path,
    source: str,
) -> None:
    calls, _ = fake_client
    content = '{"req":"001 организация"}'
    path = tmp_path / "params.json"
    path.write_text(content, encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["fns", "egr", "--params-file", str(path) if source == "file" else "-"],
        input=content.encode("utf-8") if source == "stdin" else None,
    )
    assert result.exit_code == 0
    assert calls[2][1]["req"] == "001 организация"


def test_all_terminal_controls_and_redirect(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    text = "".join(chr(i) for i in list(range(32)) + list(range(127, 160)))
    response = HttpResponse(200, "text/plain", text.encode())
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    common._render(response, None)
    assert capsys.readouterr().out == "".join(
        c if c in "\n\t" else f"\\u{ord(c):04x}" for c in text
    )
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    common._render(response, None)
    assert capsys.readouterr().out == text
