"""Инвентарь e2e-сценариев на основе исследовательских OpenAPI."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
SERVICES = (
    "fns",
    "rosstat",
    "banks",
    "scoring",
    "procurement",
    "arbitration",
    "fssp",
    "spk",
)
# Синтетические строки используются только с простыми документированными параметрами.
SAFE_STRING_PARAMS = (
    "req",
    "inn",
    "q",
    "regn",
    "docno",
    "bankbic",
    "object_id",
    "fam",
    "model",
    "pokname",
)
FILE_METHODS = {"nalogbi_file", "vyp", "mspinfo_file", "bo_file"}
SAFE_INTEGER_PARAMS = ("bankregn", "pokid", "groupid", "page", "region")


@dataclass(frozen=True)
class Operation:
    service: str
    method: str
    path: str
    query_param: str | None
    is_file: bool
    integer_param: bool = False

    def wire_value(self, generated: str) -> str:
        return str(int(generated[-1]) + 1) if self.integer_param else generated

    def sdk_value(self, generated: str) -> str | int:
        value = self.wire_value(generated)
        # Идентификаторы банков в скелете SDK — строки, хотя в Swagger часть описана числами.
        if self.integer_param and self.service != "banks":
            return int(value)
        return value

    @property
    def id(self) -> str:
        return f"{self.service}/{self.method}"


def load_spec(service: str) -> dict[str, Any]:
    path = ROOT / "docs" / "swagger" / service / "openapi.yaml"
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def _resolve_parameter(
    spec: dict[str, Any], parameter: dict[str, Any]
) -> dict[str, Any]:
    seen: set[str] = set()
    while "$ref" in parameter:
        ref = parameter["$ref"]
        if (
            not isinstance(ref, str)
            or not ref.startswith("#/")
            or re.search(r"~(?![01])", ref)
        ):
            raise ValueError(f"invalid or external $ref: {ref}")
        if ref in seen:
            raise ValueError(f"cyclic $ref: {ref}")
        seen.add(ref)
        value: Any = spec
        try:
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if isinstance(value, list):
                    if not re.fullmatch(r"0|[1-9][0-9]*", part):
                        raise ValueError(f"unresolved $ref: {ref}")
                    value = value[int(part)]
                else:
                    value = value[part]
        except (IndexError, KeyError, TypeError) as exc:
            raise ValueError(f"unresolved $ref: {ref}") from exc
        if not isinstance(value, dict):
            raise TypeError(f"non-object $ref: {ref}")
        parameter = value
    return parameter


def merged_parameters(
    spec: dict[str, Any], item: dict[str, Any]
) -> list[dict[str, Any]]:
    merged = {}
    for raw in item.get("parameters", []) + item["get"].get("parameters", []):
        parameter = _resolve_parameter(spec, raw)
        merged[(parameter["name"], parameter["in"])] = parameter
    return list(merged.values())


def operations() -> list[Operation]:
    """Собрать каждый GET из исходных спецификаций, а не из текущего SDK."""
    result: list[Operation] = []
    for service in SERVICES:
        spec = load_spec(service)
        for path, item in spec["paths"].items():
            if "get" not in item:
                continue
            method = path.rsplit("/", 1)[-1]
            parameters = merged_parameters(spec, item)
            candidates = {
                p["name"]
                for p in parameters
                if p.get("in") == "query"
                and p.get("schema", {}).get("type") == "string"
                and "enum" not in p.get("schema", {})
                and "pattern" not in p.get("schema", {})
            }
            integer_candidates = {
                p["name"]
                for p in parameters
                if p.get("in") == "query"
                and p.get("schema", {}).get("type") == "integer"
                and "enum" not in p.get("schema", {})
                and "minimum" not in p.get("schema", {})
                and "maximum" not in p.get("schema", {})
            }
            integer_param = next(
                (name for name in SAFE_INTEGER_PARAMS if name in integer_candidates),
                None,
            )
            string_param = next(
                (name for name in SAFE_STRING_PARAMS if name in candidates), None
            )
            query_param = (
                (integer_param or string_param)
                if service == "banks"
                else (string_param or integer_param)
            )
            result.append(
                Operation(
                    service=service,
                    method=method,
                    path=path,
                    query_param=query_param,
                    is_file=service == "fns" and method in FILE_METHODS,
                    integer_param=query_param is not None
                    and query_param in integer_candidates,
                )
            )
    return result


OPERATIONS = operations()
