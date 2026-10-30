"""Validate catalog syntax and cross-file consistency without starting CorelDRAW."""
from __future__ import annotations

import ast
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "catalog"
sys.path.insert(0, str(ROOT))

from corel_operator.errors import ErrorCode  # noqa: E402
from corel_operator.version import (  # noqa: E402
    BRIDGE_VERSION,
    CAPABILITY_PROFILE_ID,
    TOOL_SCHEMA_VERSION,
)

REQUIRED_FILES = (
    ROOT / "CHANGELOG.md",
    ROOT / "docs" / "capability_catalog.md",
    ROOT / "docs" / "TOOL_VERSIONING.md",
    ROOT / "docs" / "UNSUPPORTED_AND_RESEARCH_REQUIRED.md",
    CATALOG_DIR / "capability_matrix.csv",
    CATALOG_DIR / "coreldraw_x7_api_inventory.json",
    CATALOG_DIR / "enum_reference.json",
    CATALOG_DIR / "mcp_tool_registry.json",
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path.relative_to(ROOT)}")
    return value


def _server_tool_names() -> set[str]:
    server_path = ROOT / "corel_operator" / "server.py"
    tree = ast.parse(server_path.read_text(encoding="utf-8"), filename=str(server_path))
    result: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            function = decorator.func
            if isinstance(function, ast.Attribute) and function.attr == "tool":
                result.add(node.name)
                break
    return result


def _walk_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for child in value.values():
            yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)


def _require_unique(values: list[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates}")


def validate() -> dict[str, int]:
    missing_files = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.is_file()]
    if missing_files:
        raise ValueError(f"Missing required catalog files: {missing_files}")

    inventory = _read_json(CATALOG_DIR / "coreldraw_x7_api_inventory.json")
    enum_reference = _read_json(CATALOG_DIR / "enum_reference.json")
    registry = _read_json(CATALOG_DIR / "mcp_tool_registry.json")

    if registry.get("tool_schema_version") != TOOL_SCHEMA_VERSION:
        raise ValueError("Registry tool_schema_version differs from corel_operator/version.py")
    if registry.get("profile_id") != CAPABILITY_PROFILE_ID:
        raise ValueError("Registry profile_id differs from corel_operator/version.py")

    tools = registry.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("mcp_tool_registry.json must contain a non-empty tools array")

    tool_names = [tool.get("name") for tool in tools]
    if not all(isinstance(name, str) and name for name in tool_names):
        raise ValueError("Every registry record must have a non-empty string name")
    _require_unique(tool_names, "tool names")

    allowed_statuses = set(registry.get("status_values", []))
    allowed_permissions = set(registry.get("permission_values", []))
    schema_definitions = registry.get("schema_definitions", {})
    if not isinstance(schema_definitions, dict):
        raise ValueError("schema_definitions must be an object")
    for definition_name, definition_schema in schema_definitions.items():
        if not isinstance(definition_schema, dict):
            raise ValueError(f"Schema definition {definition_name!r} must be an object")
        Draft202012Validator.check_schema(definition_schema)

    result_envelope = schema_definitions.get("result_envelope", {})
    result_properties = result_envelope.get("properties", {})
    if result_properties.get("bridge_version", {}).get("const") != BRIDGE_VERSION:
        raise ValueError("Result-envelope bridge_version differs from corel_operator/version.py")
    if result_properties.get("tool_schema_version", {}).get("const") != TOOL_SCHEMA_VERSION:
        raise ValueError("Result-envelope tool_schema_version differs from corel_operator/version.py")
    if result_properties.get("profile_id", {}).get("const") != CAPABILITY_PROFILE_ID:
        raise ValueError("Result-envelope profile_id differs from corel_operator/version.py")
    expected_error_codes = {code.value for code in ErrorCode}
    catalog_error_codes = set(
        schema_definitions.get("error_detail", {})
        .get("properties", {})
        .get("code", {})
        .get("enum", [])
    )
    if catalog_error_codes != expected_error_codes:
        raise ValueError("Catalog error-code enum differs from corel_operator/errors.py")

    tool_examples = registry.get("tool_examples")
    if not isinstance(tool_examples, dict):
        raise ValueError("tool_examples must be an object")
    if set(tool_examples) != set(tool_names):
        raise ValueError(
            "Tool examples differ from registry: "
            f"missing={sorted(set(tool_names) - set(tool_examples))}, "
            f"extra={sorted(set(tool_examples) - set(tool_names))}"
        )

    for tool in tools:
        name = tool["name"]
        if tool.get("status") not in allowed_statuses:
            raise ValueError(f"{name}: invalid status {tool.get('status')!r}")
        if tool.get("permission") not in allowed_permissions:
            raise ValueError(f"{name}: invalid permission {tool.get('permission')!r}")
        if tool.get("implementation", {}).get("state") not in {"registered", "planned"}:
            raise ValueError(f"{name}: implementation.state must be registered or planned")
        if tool.get("result_contract") != "tool-schema-v1-envelope":
            raise ValueError(f"{name}: missing tool-schema-v1-envelope result contract")
        for schema_key in ("input_schema", "output_schema"):
            schema = tool.get(schema_key)
            if not isinstance(schema, dict):
                raise ValueError(f"{name}: {schema_key} must be an object")
            Draft202012Validator.check_schema(schema)
            for reference in _walk_refs(schema):
                prefix = "#/schema_definitions/"
                if not reference.startswith(prefix):
                    raise ValueError(f"{name}: unsupported schema reference {reference!r}")
                definition = reference[len(prefix):]
                if definition not in schema_definitions:
                    raise ValueError(f"{name}: missing schema definition {definition!r}")

        example = tool_examples[name]
        if not isinstance(example, dict) or not {"request", "success", "error"} <= set(example):
            raise ValueError(f"{name}: example must contain request, success, and error")
        for schema_key, example_key in (
            ("input_schema", "request"),
            ("output_schema", "success"),
            ("output_schema", "error"),
        ):
            rooted_schema = {
                "$schema": registry.get("json_schema_dialect"),
                "schema_definitions": schema_definitions,
                "allOf": [tool[schema_key]],
            }
            errors = sorted(
                Draft202012Validator(rooted_schema).iter_errors(example[example_key]),
                key=lambda error: list(error.absolute_path),
            )
            if errors:
                details = "; ".join(error.message for error in errors)
                raise ValueError(f"{name}: invalid {example_key} example: {details}")

    registered_names = {
        tool["name"] for tool in tools if tool["implementation"]["state"] == "registered"
    }
    server_names = _server_tool_names()
    if registered_names != server_names:
        raise ValueError(
            "Registered catalog tools differ from server.py: "
            f"missing={sorted(server_names - registered_names)}, "
            f"extra={sorted(registered_names - server_names)}"
        )

    members = inventory.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("coreldraw_x7_api_inventory.json must contain a non-empty members array")
    member_ids = [member.get("id") for member in members]
    if not all(isinstance(member_id, str) and member_id for member_id in member_ids):
        raise ValueError("Every API inventory record must have a non-empty string id")
    _require_unique(member_ids, "API member IDs")

    evidence_ids = {
        source.get("id") for source in inventory.get("evidence_sources", [])
        if isinstance(source, dict)
    }
    for member in members:
        unknown_evidence = set(member.get("evidence", [])) - evidence_ids
        if unknown_evidence:
            raise ValueError(f"{member['id']}: unknown evidence IDs {sorted(unknown_evidence)}")

    required_member_ids = {
        requirement
        for tool in tools
        for requirement in tool.get("api_requirements", [])
    }
    unknown_members = required_member_ids - set(member_ids)
    if unknown_members:
        raise ValueError(f"Tool registry references unknown API members: {sorted(unknown_members)}")

    with (CATALOG_DIR / "capability_matrix.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        matrix_rows = list(csv.DictReader(handle))
    matrix_names = [row.get("tool_name") for row in matrix_rows]
    if not all(isinstance(name, str) and name for name in matrix_names):
        raise ValueError("Every capability-matrix row must have a tool_name")
    _require_unique(matrix_names, "capability-matrix tool names")
    if set(matrix_names) != set(tool_names):
        raise ValueError(
            "Capability matrix differs from registry: "
            f"missing={sorted(set(tool_names) - set(matrix_names))}, "
            f"extra={sorted(set(matrix_names) - set(tool_names))}"
        )

    registry_by_name = {tool["name"]: tool for tool in tools}
    for row in matrix_rows:
        tool = registry_by_name[row["tool_name"]]
        for field in ("status", "permission", "priority"):
            if row.get(field) != tool.get(field):
                raise ValueError(
                    f"{row['tool_name']}: matrix {field}={row.get(field)!r} "
                    f"does not match registry {tool.get(field)!r}"
                )

    enums = enum_reference.get("enums")
    if not isinstance(enums, dict) or not enums:
        raise ValueError("enum_reference.json must contain a non-empty enums object")

    return {
        "registered_tools": len(registered_names),
        "registry_records": len(tools),
        "inventory_members": len(members),
        "matrix_rows": len(matrix_rows),
        "enum_groups": len(enums),
        "schemas_checked": len(tools) * 2 + len(schema_definitions),
        "examples_checked": len(tools) * 3,
    }


def main() -> None:
    counts = validate()
    print("Catalog validation passed")
    for label, value in counts.items():
        print(f"- {label}: {value}")


if __name__ == "__main__":
    main()
