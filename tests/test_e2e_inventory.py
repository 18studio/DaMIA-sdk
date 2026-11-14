"""Local Prism inventory characterization; no server or network required."""

import shutil
import socket
import subprocess
from collections.abc import Callable
from typing import Any, cast

import pytest
from e2e import operations as inventory
from test_service_contract import query_parameters, resolve_parameter


def test_inventory_merge_references_and_safe_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec: dict[str, Any] = {
        "defs": {
            "a/b~c": {"$ref": "#/defs/target"},
            "target": {"name": "inn", "in": "query", "schema": {"type": "string"}},
        },
        "paths": {
            "/synthetic": {
                "parameters": [
                    {"$ref": "#/defs/a~1b~0c"},
                    {"name": "req", "in": "query", "schema": {"type": "string"}},
                ],
                "get": {
                    "parameters": [
                        {
                            "name": "req",
                            "in": "query",
                            "schema": {"type": "string", "enum": ["restricted"]},
                        }
                    ]
                },
            }
        },
    }
    item = spec["paths"]["/synthetic"]
    assert inventory.merged_parameters(spec, item) == query_parameters(spec, item)
    monkeypatch.setattr(inventory, "SERVICES", ("fns",))
    monkeypatch.setattr(inventory, "load_spec", lambda service: spec)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: pytest.fail("network access")
    )
    result = inventory.operations()
    assert len(result) == 1 and result[0].query_param == "inn"


@pytest.mark.parametrize(
    "ref",
    ["https://example.invalid/ref", "#/missing", "#/bad~2escape", "#/loop", "#/scalar"],
)
def test_inventory_resolver_matches_contract(ref: str) -> None:
    spec = {"loop": {"$ref": "#/loop"}, "scalar": "not an object"}
    for resolver in (inventory._resolve_parameter, resolve_parameter):
        with pytest.raises((ValueError, TypeError)):
            resolver(spec, {"$ref": ref})


@pytest.mark.parametrize("resolver", [inventory._resolve_parameter, resolve_parameter])
def test_resolver_json_pointer_array_indices(
    resolver: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> None:
    parameter = {"name": "inn", "in": "query"}
    spec = {"paths": {"/x": {"get": {"parameters": [parameter]}}}}
    assert resolver(spec, {"$ref": "#/paths/~1x/get/parameters/0"}) == parameter
    for index in ("1", "-1", "01", "-", "abc"):
        with pytest.raises(ValueError, match="unresolved"):
            resolver(spec, {"$ref": f"#/paths/~1x/get/parameters/{index}"})


def test_prism_missing_npx_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from e2e import conftest

    monkeypatch.setattr(shutil, "which", lambda name: None)
    generator = cast(Any, conftest.prism_servers).__wrapped__(
        None, None, SimpleNamespace()
    )
    with pytest.raises(pytest.fail.Exception, match="npx не найден"):
        next(generator)


def test_prism_uses_npx_and_reports_launch_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from types import SimpleNamespace

    from e2e import conftest

    monkeypatch.setattr(conftest, "ROOT", tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: "/test/npx")
    monkeypatch.setattr(
        conftest, "_test_spec", lambda service, directory: directory / "spec.yaml"
    )

    def start(args: list[str], **kwargs: Any) -> Any:
        assert args[:4] == ["/test/npx", "--yes", "@stoplight/prism-cli@5.5.0", "mock"]
        raise OSError("synthetic launch failure")

    monkeypatch.setattr(subprocess, "Popen", start)
    operation = inventory.Operation("fns", "egr", "/", None, False)
    request = SimpleNamespace(
        session=SimpleNamespace(
            items=[
                SimpleNamespace(
                    callspec=SimpleNamespace(params={"operation": operation})
                )
            ]
        )
    )
    factory = SimpleNamespace(mktemp=lambda name: tmp_path)
    generator = cast(Any, conftest.prism_servers).__wrapped__(None, factory, request)
    with pytest.raises(pytest.fail.Exception, match="synthetic launch failure"):
        next(generator)


def test_prism_exited_process_fails_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from types import SimpleNamespace

    from e2e import conftest

    monkeypatch.setattr(shutil, "which", lambda name: "/test/npx")
    monkeypatch.setattr(
        conftest, "_test_spec", lambda service, directory: directory / "spec.yaml"
    )
    process = SimpleNamespace(poll=lambda: 7, returncode=7)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    stopped: list[Any] = []
    monkeypatch.setattr(conftest, "_stop_process", stopped.append)
    operation = inventory.Operation("fns", "egr", "/", None, False)
    request = SimpleNamespace(
        session=SimpleNamespace(
            items=[
                SimpleNamespace(
                    callspec=SimpleNamespace(params={"operation": operation})
                )
            ]
        )
    )
    factory = SimpleNamespace(mktemp=lambda name: tmp_path)
    generator = cast(Any, conftest.prism_servers).__wrapped__(None, factory, request)
    with pytest.raises(pytest.fail.Exception, match="завершился с кодом 7"):
        next(generator)
    assert stopped == [process]
