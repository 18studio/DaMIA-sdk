"""Изолированные локальные Prism-серверы и наблюдающие HTTP-прокси."""

import http.client
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
import yaml

from .operations import ROOT, SERVICES, Operation, load_spec

# Этот модуль подключается автоматически только в дочернем Python-процессе CLI.
CLI_NETWORK_GUARD = """\
import socket

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo

def _check_address(address):
    if isinstance(address, tuple) and address[0] != "127.0.0.1":
        raise RuntimeError("e2e: outbound network is disabled")

def _connect(sock, address):
    _check_address(address)
    return _original_connect(sock, address)

def _connect_ex(sock, address):
    _check_address(address)
    return _original_connect_ex(sock, address)

def _getaddrinfo(host, *args, **kwargs):
    if host not in ("127.0.0.1", "localhost", b"127.0.0.1", b"localhost"):
        raise RuntimeError("e2e: DNS for external hosts is disabled")
    return _original_getaddrinfo(host, *args, **kwargs)

socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.getaddrinfo = _getaddrinfo
"""


@dataclass(frozen=True)
class Exchange:
    path: str
    status: int
    body: bytes
    content_type: str


class Proxy:
    """Проксирует локальные запросы в Prism и хранит синтетические запросы теста."""

    def __init__(self, prism_port: int) -> None:
        self._records: list[Exchange] = []
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", prism_port, timeout=15
                )
                try:
                    connection.request("GET", self.path, headers={"Accept": "*/*"})
                    response = connection.getresponse()
                    body = response.read()
                    content_type = response.getheader("Content-Type", "")
                    with owner._lock:
                        owner._records.append(
                            Exchange(self.path, response.status, body, content_type)
                        )
                    self.send_response(response.status)
                    if content_type:
                        self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                finally:
                    connection.close()

            def log_message(self, format: str, *args: object) -> None:
                # В URL могут быть секреты: даже синтетические query не логируем.
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def records(self) -> list[Exchange]:
        with self._lock:
            return list(self._records)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@dataclass(frozen=True)
class LocalPrism:
    url: str
    proxy: Proxy


def _local_address(address: object) -> None:
    if isinstance(address, tuple) and address and address[0] != "127.0.0.1":
        raise RuntimeError("e2e: outbound network is disabled")


@pytest.fixture(scope="session")
def local_network_only() -> Iterator[None]:
    """Запрет реальной сети для Python-процесса тестов, включая DNS."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def connect(sock: socket.socket, address: Any) -> None:
        _local_address(address)
        original_connect(sock, address)

    def connect_ex(sock: socket.socket, address: Any) -> int:
        _local_address(address)
        return original_connect_ex(sock, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in ("127.0.0.1", "localhost", b"127.0.0.1", b"localhost"):
            raise RuntimeError("e2e: DNS for external hosts is disabled")
        return original_getaddrinfo(host, *args, **kwargs)

    with (
        patch.object(socket.socket, "connect", connect),
        patch.object(socket.socket, "connect_ex", connect_ex),
        patch.object(socket, "getaddrinfo", getaddrinfo),
    ):
        yield


def _test_spec(service: str, directory: Path) -> Path:
    """Дополнить 3 неопределённых ответа синтетическими примерами для Prism.

    Исходные документы не меняются: эти значения не являются контрактом DaMIA.
    Без подстановки Prism 5.5.0 отвечает 500 на необобщённые схемы этих методов.
    """
    spec = load_spec(service)
    if service == "procurement":
        spec["paths"]["/zmon"]["get"]["responses"]["2XX"]["content"] = {
            "text/plain": {"schema": {"type": "string"}, "example": "prism-e2e-zmon"}
        }
    if service == "spk":
        for path in ("/report", "/proverki"):
            spec["paths"][path]["get"]["responses"]["2XX"]["content"] = {
                "application/json": {
                    "schema": {"type": "object"},
                    "example": {"mock": True, "operation": path[1:]},
                }
            }
    output = directory / f"{service}.yaml"
    output.write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return output


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=10)


@pytest.fixture(scope="session")
def cli_guard_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("cli-network-guard")
    (path / "sitecustomize.py").write_text(CLI_NETWORK_GUARD, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(path), "PYTHONNOUSERSITE": "1"}
    probe = subprocess.run(
        [sys.executable, "-c", "import socket; socket.getaddrinfo('example.com', 443)"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if (
        probe.returncode == 0
        or "DNS for external hosts is disabled" not in probe.stderr
    ):
        pytest.fail("Не удалось активировать защиту от внешней сети для CLI.")
    return path


@pytest.fixture(scope="session")
def prism_servers(
    local_network_only: None,
    tmp_path_factory: pytest.TempPathFactory,
    request: pytest.FixtureRequest,
) -> Iterator[dict[str, LocalPrism]]:
    """Запустить Prism только для выбранных тестов и завершить процессы."""
    npx = shutil.which("npx")
    if npx is None:
        pytest.fail("Для e2e необходимы Node.js и npx; Prism не запущен.")
    directory = tmp_path_factory.mktemp("prism-e2e")
    servers: dict[str, LocalPrism] = {}
    selected = {
        operation.service
        for item in request.session.items
        if (callspec := getattr(item, "callspec", None)) is not None
        if isinstance((operation := callspec.params.get("operation")), Operation)
    }
    with ExitStack() as stack:
        for service in SERVICES:
            if service not in selected:
                continue
            spec = _test_spec(service, directory)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = cast(int, sock.getsockname()[1])
            log = stack.enter_context((directory / f"{service}.log").open("w+b"))
            process = subprocess.Popen(
                [
                    npx,
                    "--yes",
                    "@stoplight/prism-cli@5.5.0",
                    "mock",
                    str(spec),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
            )
            stack.callback(_stop_process, process)
            deadline = time.monotonic() + 60
            while True:
                if process.poll() is not None:
                    log.flush()
                    pytest.fail(
                        f"Prism {service} завершился с кодом {process.returncode}; см. {log.name}"
                    )
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        pytest.fail(
                            f"Prism {service} не запустился за 60 секунд; см. {log.name}"
                        )
                    time.sleep(0.1)
            proxy = Proxy(port)
            stack.callback(proxy.close)
            servers[service] = LocalPrism(f"http://127.0.0.1:{port}", proxy)
        yield servers
