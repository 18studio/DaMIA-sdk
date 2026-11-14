"""Общие средства регистрации безопасных CLI-заготовок."""

import asyncio
import importlib
import inspect
import json
import os
import sys
from collections.abc import Callable, Mapping
from typing import Any, get_args, get_origin, get_type_hints

import typer
from typer.core import TyperCommand, TyperGroup

# Typer may use either external Click or its vendored implementation.
_click_package = TyperCommand.__mro__[1].__module__.rsplit(".", 1)[0]
UsageError = importlib.import_module(f"{_click_package}.exceptions").UsageError


from damia_sdk.client import DamiaClient
from damia_sdk.settings import DamiaSettings
from damia_sdk.transport.response import HttpResponse


class SafeCommand(TyperCommand):
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            ctx.fail("Ошибка параметров.")
            raise


class SafeGroup(TyperGroup):
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            ctx.fail("Ошибка параметров.")
            raise

    def resolve_command(self, ctx: Any, args: list[str]) -> Any:
        try:
            return super().resolve_command(ctx, args)
        except UsageError:
            ctx.fail("Ошибка параметров.")
            raise


def _kind(annotation: object) -> str:
    parts = get_args(annotation)
    if any(get_origin(item) is Mapping for item in parts):
        return "mapping"
    if any(get_origin(item) is list for item in parts):
        return "list"
    if int in parts or annotation is int:
        return "integer"
    return "string"


def _cli_signature(
    method: Callable[..., Any], *, file_output: bool = False
) -> inspect.Signature:
    hints = get_type_hints(method)
    parameters = []
    for parameter in inspect.signature(method).parameters.values():
        if parameter.name == "self":
            continue
        kind = _kind(hints[parameter.name])
        option = "--" + parameter.name.replace("_", "-")
        help_text = None
        annotation: object = str | None
        if kind == "mapping":
            option = "--balance-field"
            annotation = list[str]
            help_text = "Повторяйте NAME=INTEGER для каждого поля."
        elif kind == "list":
            annotation = list[str]
            help_text = "Повторяйте опцию для каждого значения; порядок сохраняется."
        elif hints[parameter.name] is object:
            help_text = "Строка без интерпретации."
        parameters.append(
            parameter.replace(
                annotation=annotation,
                default=typer.Option(None, option, help=help_text),
            )
        )
    parameters.append(
        inspect.Parameter(
            "ctx", inspect.Parameter.KEYWORD_ONLY, annotation=typer.Context
        )
    )
    parameters.append(
        inspect.Parameter(
            "params_file",
            inspect.Parameter.KEYWORD_ONLY,
            annotation=str | None,
            default=typer.Option(
                None,
                "--params-file",
                help="UTF-8 JSON объект параметров; - означает stdin.",
            ),
        )
    )
    if file_output:
        parameters.append(
            inspect.Parameter(
                "output",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=str,
                default=typer.Option(
                    ..., "--output", help="Новый файл для байтов ответа."
                ),
            )
        )
    return inspect.Signature(parameters=parameters)


def convert_parameters(
    method: Callable[..., Any], values: Mapping[str, Any]
) -> dict[str, Any]:
    """Преобразовать разобранные строки в аргументы SDK без вывода значений."""
    hints = get_type_hints(method)
    result = dict(values)
    for name, value in values.items():
        kind = _kind(hints[name])
        option = (
            "--balance-field" if kind == "mapping" else "--" + name.replace("_", "-")
        )
        if kind == "list":
            result[name] = value or None
        elif kind == "integer" and value is not None:
            try:
                result[name] = int(value)
            except ValueError:
                raise ValueError(f"{option}: ожидается целое число") from None
        elif kind == "mapping":
            if not value:
                result[name] = None
                continue
            fields: dict[str, int] = {}
            for item in value:
                key, separator, number = item.partition("=")
                if not separator or not key or key in fields:
                    raise ValueError(f"{option}: неверное или повторное имя поля")
                try:
                    fields[key] = int(number)
                except ValueError:
                    raise ValueError(f"{option}: ожидается целое число") from None
            result[name] = fields
    return result


FILE_METHODS = frozenset({"nalogbi_file", "vyp", "mspinfo_file", "bo_file"})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _file_parameters(method: Callable[..., Any], path: str) -> dict[str, Any]:
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as stream:
            text = stream.read()
    try:
        data = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except RecursionError:
        raise ValueError("JSON nesting too deep") from None
    hints = get_type_hints(method)
    if not isinstance(data, dict) or any(
        key not in hints or key == "return" for key in data
    ):
        raise ValueError("invalid fields")
    for key, value in data.items():
        kind = _kind(hints[key])
        valid = value is None
        if kind == "integer":
            valid |= type(value) is int
        elif kind == "list":
            valid |= isinstance(value, list) and all(
                isinstance(item, str) for item in value
            )
        elif kind == "mapping":
            valid |= isinstance(value, dict) and all(
                isinstance(k, str) and k and type(v) is int for k, v in value.items()
            )
        else:
            valid |= isinstance(value, str)
        if not valid:
            raise ValueError("invalid type")
        if kind == "list" and value == []:
            data[key] = None
    return data


def _write_output(path: str, body: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    stat = None
    try:
        stat = os.fstat(fd)
        stream = os.fdopen(fd, "wb")
        fd = -1  # The stream owns the descriptor after fdopen succeeds.
        with stream:
            stream.write(body)
    except BaseException:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        if stat is not None:
            try:
                current = os.lstat(path)
                if (current.st_dev, current.st_ino) == (stat.st_dev, stat.st_ino):
                    os.unlink(path)
            except OSError:
                pass
        raise


def _safe_terminal(text: str) -> str:
    return "".join(
        f"\\u{ord(c):04x}"
        if (ord(c) < 32 and c not in "\n\t") or 127 <= ord(c) <= 159
        else c
        for c in text
    )


def _render(response: HttpResponse, output: str | None) -> None:
    if output is not None:
        _write_output(output, response.body)
        return
    media = (response.content_type or "").split(";", 1)[0].strip().lower()
    if media == "application/json" or media.endswith("+json"):
        text = json.dumps(response.data, ensure_ascii=True, allow_nan=False)
        if sys.stdout.isatty():
            text = _safe_terminal(text)
        typer.echo(text)
    elif media.startswith("text/"):
        text = response.text
        if sys.stdout.isatty():
            text = _safe_terminal(text)
        typer.echo(text, nl=False)
    else:
        raise ValueError("binary response")


def _command(
    method: Callable[..., Any], service: str, name: str
) -> Callable[..., None]:
    file_output = service == "fns" and name in FILE_METHODS

    def command(**kwargs: Any) -> None:
        context = kwargs.pop("ctx")
        params_file = kwargs.pop("params_file")
        output = kwargs.pop("output", None)
        try:
            params = convert_parameters(method, kwargs)
            if params_file is not None:
                file_params = _file_parameters(method, params_file)
                if any(
                    context.get_parameter_source(key).name == "COMMANDLINE"
                    for key in file_params
                ):
                    raise ValueError("conflict")
                params.update(file_params)
        except (ValueError, TypeError, OSError, UnicodeError):
            typer.echo("Ошибка параметров.", err=True)
            raise typer.Exit(code=2) from None

        async def invoke() -> HttpResponse:
            settings = DamiaSettings.from_env()
            async with DamiaClient(settings=settings) as client:
                return await getattr(getattr(client, service), name)(**params)  # type: ignore[no-any-return]

        try:
            _render(asyncio.run(invoke()), output)
        except Exception:  # noqa: BLE001
            typer.echo("Ошибка выполнения команды.", err=True)
            raise typer.Exit(code=1) from None

    setattr(command, "__signature__", _cli_signature(method, file_output=file_output))  # noqa: B010
    return command


def create_service_app(
    service: str,
    service_class: type[object],
    methods: tuple[str, ...],
    *,
    help_text: str,
) -> typer.Typer:
    """Создать группу только с явно перечисленными методами SDK."""
    app = typer.Typer(help=help_text, no_args_is_help=True, cls=SafeGroup)
    for name in methods:
        method = getattr(service_class, name)
        cli_name = name.replace("_", "-")
        app.command(
            name=cli_name,
            cls=SafeCommand,
            help=f"Вызов {service} {cli_name}."
            + (
                " Может изменять состояние."
                if (service, name)
                in {("fns", "mon"), ("procurement", "zmon"), ("arbitration", "delopro")}
                else ""
            ),
        )(_command(method, service, name))
    return app
