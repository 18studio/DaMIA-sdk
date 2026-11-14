"""Снимок исследовательских спецификаций, не наблюдение сервера.

Нормализация v2: сортировка mapping, порядок списков сохраняется; $ref
раскрывается с сохранением указателя и siblings, цикл обозначается указателем.
"""

import ast
import copy
import hashlib
import inspect
import json
import sys
import types
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict, cast

import pytest
import yaml


class SDKParameter(TypedDict):
    annotation: str
    default: str


class SDKMethod(TypedDict):
    route: list[str]
    signature: str
    parameters: dict[str, SDKParameter]
    source: str


ParameterEntry = TypedDict(
    "ParameterEntry",
    {
        "wire": str,
        "in": str,
        "python": str | None,
        "spec": Any,
        "sdk": SDKParameter | None,
    },
)


class MediaEntry(TypedDict):
    schema_present: bool
    schema: Any
    graph_sha256: str | None


class ResponseEntry(TypedDict):
    source: Any
    media: dict[str, MediaEntry]


class SecurityEntry(TypedDict):
    requirements: Any
    schemes: Any


class Operation(TypedDict):
    service: str
    http: str
    path: str
    sdk_method: str | None
    sdk: SDKMethod | None
    parameters: list[ParameterEntry]
    unmatched_sdk_parameters: list[str]
    security: SecurityEntry
    responses: dict[str, ResponseEntry]
    spec_source: str
    research_source: str


Methods = dict[str, SDKMethod]


class Inventory(TypedDict):
    normalization: str
    operations: list[Operation]
    unmatched_sdk_methods: dict[str, Methods]


ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "fns",
    "banks",
    "procurement",
    "arbitration",
    "fssp",
    "rosstat",
    "scoring",
    "spk",
)
SNAPSHOT = ROOT / "docs/contracts/inventory.yaml"


def resolve(doc: Any, ref: Any) -> Any:
    if ref == "#":
        return doc
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(f"external or invalid $ref: {ref}")
    node = doc
    try:
        for token in ref[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            node = node[int(token)] if isinstance(node, list) else node[token]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ValueError(f"unresolved $ref: {ref}") from exc
    return node


def graph(doc: Any, node: Any, active: tuple[str, ...] = ()) -> Any:
    if isinstance(node, list):
        return [graph(doc, item, active) for item in node]
    if not isinstance(node, dict):
        return node
    fields = {k: graph(doc, v, active) for k, v in sorted(node.items())}
    if "$ref" not in node:
        return fields
    ref = node["$ref"]
    target = resolve(doc, ref)  # validate even cyclic references
    return {
        "fields": fields,
        "target": {"cycle": ref}
        if ref in active
        else {"value": graph(doc, target, (*active, ref))},
    }


def resolve_object(doc: Any, obj: Any, kind: str) -> Any:
    active: set[str] = set()
    while "$ref" in obj:
        ref = obj["$ref"]
        if ref in active:
            raise ValueError(f"cyclic {kind} $ref: {ref}")
        active.add(ref)
        obj = resolve(doc, ref)
    return obj


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def sdk_methods(service: str) -> Methods:
    path = ROOT / "src/damia_sdk/services" / service / "__init__.py"
    tree = ast.parse(path.read_text())
    methods: Methods = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for fn in (
            n
            for n in cls.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        ):
            calls = [
                n
                for n in ast.walk(fn)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "request"
            ]
            routes = [
                (
                    cast(str, cast(ast.Constant, c.args[0]).value),
                    cast(str, cast(ast.Constant, c.args[1]).value),
                )
                for c in calls
                if len(c.args) >= 2
                and all(
                    isinstance(a, ast.Constant) and isinstance(a.value, str)
                    for a in c.args[:2]
                )
            ]
            if not routes:
                routes = [
                    ("GET", n.args[0].value)
                    for n in ast.walk(fn)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "_get"
                    and n.args
                    and isinstance(n.args[0], ast.Constant)
                    and isinstance(n.args[0].value, str)
                ]
            if len(routes) != 1:
                raise ValueError(f"unmapped SDK method {service}.{fn.name}: {routes}")
            module = __import__(f"damia_sdk.services.{service}", fromlist=[cls.name])
            method = getattr(getattr(module, cls.name), fn.name)
            signature = inspect.signature(method)
            methods[fn.name] = {
                "route": list(routes[0]),
                "signature": str(signature),
                "parameters": {
                    name: {"annotation": str(p.annotation), "default": repr(p.default)}
                    for name, p in signature.parameters.items()
                    if name != "self"
                },
                "source": f"src/damia_sdk/services/{service}/__init__.py#L{fn.lineno}",
            }
    return methods


def extract(service: str, doc: dict[str, Any], methods: Methods) -> list[Operation]:
    result: list[Operation] = []
    for path, item in sorted(doc["paths"].items()):
        for verb in (
            "get",
            "put",
            "post",
            "delete",
            "options",
            "head",
            "patch",
            "trace",
        ):
            if verb not in item:
                continue
            op = item[verb]
            matches = [
                (name, m)
                for name, m in methods.items()
                if m["route"] == [verb.upper(), path]
            ]
            if len(matches) > 1:
                raise ValueError(f"ambiguous SDK mapping {service} {path}")
            name, method = matches[0] if matches else (None, None)
            parameters: dict[tuple[str, str], tuple[Any, Any]] = {}
            for raw in item.get("parameters", []) + op.get("parameters", []):
                p = resolve_object(doc, raw, "parameter")
                parameters[(p["name"], p["in"])] = (raw, p)
            entries: list[ParameterEntry] = []
            for (wire, location), (raw, p) in sorted(parameters.items()):
                python = wire[:-2] + "_list" if wire.endswith("[]") else wire
                matched = python if method and python in method["parameters"] else None
                entries.append(
                    {
                        "wire": wire,
                        "in": location,
                        "python": matched,
                        "spec": graph(doc, raw),
                        "sdk": cast(SDKMethod, method)["parameters"][matched]
                        if matched
                        else None,
                    }
                )
            responses: dict[str, ResponseEntry] = {}
            for status, raw in sorted(
                op.get("responses", {}).items(), key=lambda x: str(x[0])
            ):
                response = resolve_object(doc, raw, "response")
                media: dict[str, MediaEntry] = {}
                for mime, content in sorted(response.get("content", {}).items()):
                    schema = content.get("schema")
                    media[mime] = {
                        "schema_present": "schema" in content,
                        "schema": schema,
                        "graph_sha256": digest(graph(doc, schema))
                        if "schema" in content
                        else None,
                    }
                responses[str(status)] = {"source": raw, "media": media}
            result.append(
                {
                    "service": service,
                    "http": verb.upper(),
                    "path": path,
                    "sdk_method": name,
                    "sdk": method,
                    "parameters": entries,
                    "unmatched_sdk_parameters": sorted(
                        set(method["parameters"])
                        - {p["python"] for p in entries if p["python"]}
                    )
                    if method
                    else [],
                    "security": {
                        "requirements": op.get("security", doc.get("security")),
                        "schemes": doc.get("components", {}).get("securitySchemes", {}),
                    },
                    "responses": responses,
                    "spec_source": f"docs/swagger/{service}/openapi.yaml#/paths/{path.replace('~', '~0').replace('/', '~1')}/{verb}",
                    "research_source": f"docs/swagger/{service}/RESEARCH.md",
                }
            )
    return result


def current() -> Inventory:
    operations: list[Operation] = []
    unmatched: dict[str, Methods] = {}
    for service in SERVICES:
        doc = yaml.safe_load(
            (ROOT / "docs/swagger" / service / "openapi.yaml").read_text()
        )
        methods = sdk_methods(service)
        entries = extract(service, doc, methods)
        operations.extend(entries)
        matched = {e["sdk_method"] for e in entries}
        unmatched[service] = {k: v for k, v in methods.items() if k not in matched}
    return {
        "normalization": "schema-graph-v2",
        "operations": operations,
        "unmatched_sdk_methods": unmatched,
    }


def test_snapshot_matches_sources() -> None:
    expected = yaml.safe_load(SNAPSHOT.read_text())
    actual = current()
    assert actual["normalization"] == expected["normalization"]
    assert actual["unmatched_sdk_methods"] == expected["unmatched_sdk_methods"]

    def indexed(entries: list[Operation]) -> dict[tuple[str, str, str], Operation]:
        index = {(e["service"], e["http"], e["path"]): e for e in entries}
        assert len(index) == len(entries)
        return index

    a, e = indexed(actual["operations"]), indexed(expected["operations"])
    assert a.keys() == e.keys()
    for key in e:
        for field in (
            "sdk_method",
            "sdk",
            "parameters",
            "unmatched_sdk_parameters",
            "security",
            "responses",
            "spec_source",
            "research_source",
        ):
            assert (
                cast(Mapping[str, object], a[key])[field]
                == cast(Mapping[str, object], e[key])[field]
            ), (key, field)


def test_baseline_counts() -> None:
    snapshot = SNAPSHOT.read_bytes()
    # This distribution describes only the original snapshot, not later API versions.
    if hashlib.sha256(snapshot).hexdigest() != (
        "b05f658348ed01b0e1dd3d5ba7141fbf0877f69ab0976c9f95e3868cef08df14"
    ):
        pytest.skip("distribution applies only to the original snapshot")
    entries = yaml.safe_load(snapshot)["operations"]
    assert Counter(e["service"] for e in entries) == {
        "fns": 24,
        "banks": 9,
        "procurement": 12,
        "arbitration": 4,
        "fssp": 4,
        "rosstat": 3,
        "scoring": 3,
        "spk": 2,
    }


def test_updated_snapshot_allows_new_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = yaml.safe_load(SNAPSHOT.read_text())
    operation = copy.deepcopy(snapshot["operations"][0])
    operation["path"] = "/synthetic-new-operation"
    snapshot["operations"].append(operation)
    updated = tmp_path / "inventory.yaml"
    updated.write_text(yaml.safe_dump(snapshot))
    monkeypatch.setattr(sys.modules[__name__], "SNAPSHOT", updated)
    monkeypatch.setattr(sys.modules[__name__], "current", lambda: snapshot)
    test_snapshot_matches_sources()
    with pytest.raises(pytest.skip.Exception):
        test_baseline_counts()
    snapshot["operations"].pop()
    with pytest.raises(AssertionError):
        test_snapshot_matches_sources()


def test_new_sync_sdk_method_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "src/damia_sdk/services/synthetic/__init__.py"
    source.parent.mkdir(parents=True)
    spec = tmp_path / "docs/swagger/synthetic/openapi.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text("paths: {}\n")
    module = types.ModuleType("damia_sdk.services.synthetic")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "SERVICES", ("synthetic",))
    snapshot = tmp_path / "inventory.yaml"
    monkeypatch.setattr(sys.modules[__name__], "SNAPSHOT", snapshot)

    source.write_text("class Synthetic:\n    pass\n")
    class_name = "Synthetic"
    setattr(module, class_name, type("Synthetic", (), {}))
    snapshot.write_text(yaml.safe_dump(current()))
    test_snapshot_matches_sources()

    source.write_text(
        "class Synthetic:\n"
        "    def new_method(self: Any) -> Any:\n"
        "        return self._get('/synthetic')\n"
    )

    def new_method(self: Any) -> Any:
        return self._get("/synthetic")

    setattr(module, class_name, type("Synthetic", (), {"new_method": new_method}))
    assert "new_method" in current()["unmatched_sdk_methods"]["synthetic"]
    with pytest.raises(AssertionError):
        test_snapshot_matches_sources()


def test_root_ref_graph_cycle() -> None:
    doc: dict[str, Any] = {"$ref": "#"}
    assert resolve(doc, "#") is doc
    assert graph(doc, doc) == {
        "fields": {"$ref": "#"},
        "target": {"value": {"fields": {"$ref": "#"}, "target": {"cycle": "#"}}},
    }
    assert resolve({"": "empty key"}, "#/") == "empty key"


def test_graph_references_and_normalization() -> None:
    doc: dict[str, Any] = {
        "components": {
            "schemas": {
                "a/b~c": {
                    "properties": {"nested": {"$ref": "#/components/schemas/loop"}}
                },
                "loop": {"items": {"$ref": "#/components/schemas/loop"}},
            }
        }
    }
    ref = {"$ref": "#/components/schemas/a~1b~0c"}
    before = graph(doc, ref)
    assert (
        before["target"]["value"]["properties"]["nested"]["target"]["value"]["items"][
            "target"
        ]["cycle"]
        == "#/components/schemas/loop"
    )
    assert digest(graph(doc, {"b": 2, "a": [1, 2]})) == digest(
        graph(doc, {"a": [1, 2], "b": 2})
    )
    assert digest(graph(doc, {"a": [1, 2]})) != digest(graph(doc, {"a": [2, 1]}))
    changed = copy.deepcopy(doc)
    changed["components"]["schemas"]["loop"]["type"] = "array"
    assert digest(graph(changed, ref)) != digest(before)
    for bad in ("https://example.invalid/schema", "#/missing"):
        with pytest.raises(ValueError):
            graph(doc, {"$ref": bad})


@pytest.mark.parametrize(
    "mutation",
    [
        "add_operation",
        "add_post_operation",
        "delete_operation",
        "add_parameter",
        "delete_parameter",
        "add_response",
        "delete_response",
        "nested_schema",
        "ref_target_sibling",
    ],
)
def test_synthetic_mutations_detected(
    mutation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc: dict[str, Any] = {
        "paths": {
            "/x": {
                "get": {
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/response"}
                                }
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "response": {
                    "properties": {
                        "nested": {
                            "$ref": "#/components/schemas/value",
                            "$target": "original",
                        }
                    }
                },
                "value": {"type": "string"},
            }
        },
    }
    baseline = {
        "normalization": "schema-graph-v2",
        "operations": extract("synthetic", doc, {}),
        "unmatched_sdk_methods": {},
    }
    snapshot = tmp_path / "inventory.yaml"
    snapshot.write_text(yaml.safe_dump(baseline))
    monkeypatch.setattr(sys.modules[__name__], "SNAPSHOT", snapshot)
    monkeypatch.setattr(sys.modules[__name__], "current", lambda: baseline)
    test_snapshot_matches_sources()
    changed = copy.deepcopy(doc)
    op = changed["paths"]["/x"]["get"]
    if mutation == "add_operation":
        changed["paths"]["/y"] = copy.deepcopy(changed["paths"]["/x"])
    elif mutation == "add_post_operation":
        changed["paths"]["/x"]["post"] = copy.deepcopy(op)
    elif mutation == "delete_operation":
        del changed["paths"]["/x"]
    elif mutation == "add_parameter":
        op["parameters"].append({"name": "n", "in": "query"})
    elif mutation == "delete_parameter":
        op["parameters"].clear()
    elif mutation == "add_response":
        op["responses"]["400"] = {"description": "synthetic"}
    elif mutation == "delete_response":
        op["responses"].clear()
    elif mutation == "nested_schema":
        changed["components"]["schemas"]["value"]["type"] = "integer"
    else:
        changed["components"]["schemas"]["response"]["properties"]["nested"][
            "$target"
        ] = "changed"
    actual = {**baseline, "operations": extract("synthetic", changed, {})}
    monkeypatch.setattr(sys.modules[__name__], "current", lambda: actual)
    with pytest.raises(AssertionError):
        test_snapshot_matches_sources()


def test_parameter_ref_chain_and_cycles() -> None:
    doc: dict[str, Any] = {
        "paths": {
            "/x": {"get": {"parameters": [{"$ref": "#/components/parameters/first"}]}}
        },
        "components": {
            "parameters": {
                "first": {"$ref": "#/components/parameters/second"},
                "second": {"name": "q", "in": "query"},
            }
        },
    }
    entries = extract("synthetic", doc, {})
    assert entries[0]["parameters"][0]["wire"] == "q"
    doc["components"]["parameters"]["second"] = {
        "$ref": "#/components/parameters/first"
    }
    with pytest.raises(ValueError, match=r"cyclic parameter \$ref"):
        extract("synthetic", doc, {})
    for ref in ("#/missing", "https://example.invalid/parameter"):
        doc["components"]["parameters"]["second"] = {"$ref": ref}
        with pytest.raises(ValueError):
            extract("synthetic", doc, {})


def test_response_ref_chain_detects_nested_schema_changes_and_cycles() -> None:
    doc: dict[str, Any] = {
        "paths": {
            "/x": {
                "get": {"responses": {"200": {"$ref": "#/components/responses/first"}}}
            }
        },
        "components": {
            "responses": {
                "first": {"$ref": "#/components/responses/second"},
                "second": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/body"}
                        }
                    }
                },
            },
            "schemas": {"body": {"properties": {"nested": {"type": "string"}}}},
        },
    }
    baseline = extract("synthetic", doc, {})
    assert "application/json" in baseline[0]["responses"]["200"]["media"]
    changed = copy.deepcopy(doc)
    changed["components"]["schemas"]["body"]["properties"]["nested"]["type"] = "integer"
    assert extract("synthetic", changed, {}) != baseline
    changed["components"]["responses"]["second"] = {
        "$ref": "#/components/responses/first"
    }
    with pytest.raises(ValueError, match=r"cyclic response \$ref"):
        extract("synthetic", changed, {})


def validate_refs(doc: Any, node: Any) -> None:
    if isinstance(node, list):
        for value in node:
            validate_refs(doc, value)
    elif isinstance(node, dict):
        if "$ref" in node:
            resolve(doc, node["$ref"])
        for value in node.values():
            validate_refs(doc, value)


def test_all_spec_refs_resolve() -> None:
    for service in SERVICES:
        doc = yaml.safe_load(
            (ROOT / "docs/swagger" / service / "openapi.yaml").read_text()
        )
        validate_refs(doc, doc)


def test_operation_parameter_overrides_path_parameter() -> None:
    doc: dict[str, Any] = {
        "paths": {
            "/x": {
                "parameters": [{"name": "q", "in": "query", "required": True}],
                "get": {
                    "parameters": [{"name": "q", "in": "query", "required": False}],
                    "responses": {},
                },
            }
        }
    }
    params = extract("synthetic", doc, {})[0]["parameters"]
    assert len(params) == 1
    assert params[0]["spec"]["required"] is False


@pytest.mark.parametrize(("service", "expected_count"), [("fns", 24), ("banks", 9)])
def test_post_research_metadata_is_not_executable(
    service: str, expected_count: int
) -> None:
    doc = yaml.safe_load((ROOT / "docs/swagger" / service / "openapi.yaml").read_text())
    paths = doc["paths"]
    assert len(paths) == expected_count
    for path, item in paths.items():
        assert "get" in item, path
        assert "post" not in item, path
        assert item["x-post-contract"]["sdk-ready"] is False, path


@pytest.mark.parametrize("service", SERVICES)
def test_no_executable_post_operations(service: str) -> None:
    doc = yaml.safe_load((ROOT / "docs/swagger" / service / "openapi.yaml").read_text())
    assert all("post" not in item for item in doc["paths"].values())
