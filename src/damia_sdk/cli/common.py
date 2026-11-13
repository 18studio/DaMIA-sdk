"""Общие средства регистрации безопасных CLI-заготовок."""

import inspect
from collections.abc import Callable, Mapping
from typing import Any, get_args, get_origin, get_type_hints

import typer


def _cli_annotation(annotation: object) -> object:
    """Преобразовать неподдерживаемые или неизвестные типы в строковую опцию.

    На этапе заглушки значения не разбираются и не передаются в SDK.
    """
    if annotation is object or any(
        get_origin(item) is Mapping for item in get_args(annotation)
    ):
        return str | None
    return annotation


def _stub_command(
    method: Callable[..., Any], service: str, name: str
) -> Callable[..., None]:
    """Создать CLI-заглушку с параметрами из явно зарегистрированного метода SDK."""
    signature = inspect.signature(method)
    hints = get_type_hints(method)
    parameters = [
        parameter.replace(annotation=_cli_annotation(hints[parameter.name]))
        for parameter in signature.parameters.values()
        if parameter.name != "self"
    ]

    def command(**kwargs: object) -> None:
        # Значения аргументов не выводятся: они могут содержать персональные данные.
        typer.echo(f"Команда {service} {name} пока не реализована.", err=True)
        raise typer.Exit(code=1)

    # Typer использует сигнатуру для построения help и проверки типов опций.
    setattr(command, "__signature__", inspect.Signature(parameters=parameters))  # noqa: B010
    return command


def create_service_app(
    service: str,
    service_class: type[object],
    methods: tuple[str, ...],
    *,
    help_text: str,
) -> typer.Typer:
    """Создать группу только с явно перечисленными методами SDK."""
    app = typer.Typer(help=help_text, no_args_is_help=True)
    for name in methods:
        method = getattr(service_class, name)
        cli_name = name.replace("_", "-")
        app.command(name=cli_name, help=f"Заготовка команды {service} {cli_name}.")(
            _stub_command(method, service, cli_name)
        )
    return app
