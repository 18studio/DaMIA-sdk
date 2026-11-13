"""E2E CLI: отдельный процесс `damia` обращается к локальному Prism."""

import json
import os
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from hypothesis import Phase, given, settings
from hypothesis import strategies as st

from .conftest import LocalPrism
from .operations import OPERATIONS, SERVICES, Operation


def cli_environment(
    servers: dict[str, LocalPrism], guard_dir: Path, key: str
) -> dict[str, str]:
    # Реальные ключи и адреса из окружения разработчика не наследуются.
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("DAMIA_", "SENTRY_"))
        and name
        not in {
            "PYTHONPATH",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        }
    }
    env.update(
        {
            "PYTHONPATH": str(guard_dir),
            "PYTHONNOUSERSITE": "1",
            "NO_PROXY": "127.0.0.1,localhost",
            "DAMIA_FNS_KEY": key,
            "DAMIA_BANKS_KEY": key,
            "DAMIA_API_KEY": key,
        }
    )
    for service in SERVICES:
        env[f"DAMIA_BASE_URLS__{service.upper()}"] = (
            servers[service].proxy.url if service in servers else "http://127.0.0.2:1"
        )
    return env


@pytest.mark.e2e
@pytest.mark.parametrize("operation", OPERATIONS, ids=lambda op: op.id)
@settings(
    max_examples=3,
    deadline=None,
    database=None,
    phases=(Phase.explicit, Phase.generate),
    report_multiple_bugs=False,
)
@given(value=st.text(alphabet="0123456789", min_size=10, max_size=10))
def test_cli_command_against_prism(
    operation: Operation,
    prism_servers: dict[str, LocalPrism],
    cli_guard_dir: Path,
    value: str,
) -> None:
    key = f"synthetic-key-{value}"
    params = {"key": key}
    args = [operation.service, operation.method.replace("_", "-")]
    if operation.query_param is not None:
        query_value = operation.wire_value(value)
        params[operation.query_param] = query_value
        args.extend([f"--{operation.query_param.replace('_', '-')}", query_value])
    if operation.service == "spk" and operation.method == "report":
        params["format"] = "json"
        args.extend(["--format", "json"])

    prism = prism_servers[operation.service]
    with httpx.Client(trust_env=False, timeout=10) as baseline:
        expected = baseline.get(prism.url + operation.path, params=params)
    assert expected.status_code == 200, (
        operation.id,
        expected.status_code,
        expected.text,
    )

    executable = Path(sysconfig.get_path("scripts")) / (
        "damia.exe" if os.name == "nt" else "damia"
    )
    assert executable.is_file(), f"CLI entrypoint не установлен: {executable}"
    with tempfile.TemporaryDirectory(prefix="damia-e2e-") as directory:
        output_file = Path(directory) / "result.bin"
        if operation.is_file:
            args.extend(["--output", str(output_file)])
        prism.proxy.clear()
        result = subprocess.run(
            [str(executable), *args],
            env=cli_environment(prism_servers, cli_guard_dir, key),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, (operation.id, result.stderr)
        requests = prism.proxy.records()
        assert len(requests) == 1, f"{operation.id}: ожидался ровно один запрос к Prism"
        parsed = urlsplit(requests[0].path)
        assert parsed.path == operation.path
        forwarded = parse_qs(parsed.query, keep_blank_values=True)
        for name, expected_value in params.items():
            assert forwarded.get(name) == [expected_value], (operation.id, name)
        assert requests[0].status == expected.status_code
        content_type = expected.headers.get("Content-Type", "")
        if operation.is_file:
            assert output_file.read_bytes() == expected.content
            assert result.stdout == ""
        elif "json" in content_type:
            assert json.loads(result.stdout) == expected.json()
        else:
            assert result.stdout.rstrip("\n") == expected.text.rstrip("\n")
        assert key not in result.stdout
        assert key not in result.stderr


@pytest.mark.e2e
def test_cli_network_guard_is_active(cli_guard_dir: Path) -> None:
    env = cli_environment({}, cli_guard_dir, "synthetic-key")
    result = subprocess.run(
        [sys.executable, "-c", "import socket; socket.getaddrinfo('example.com', 443)"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode != 0
    assert "DNS for external hosts is disabled" in result.stderr
