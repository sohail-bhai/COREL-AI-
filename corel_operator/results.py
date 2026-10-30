"""Stable JSON-compatible result envelopes for MCP tools."""
from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Mapping

from .errors import CorelBridgeError, ErrorCode
from .version import BRIDGE_VERSION, CAPABILITY_PROFILE_ID, TOOL_SCHEMA_VERSION


def _duration(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _target_document(data: Mapping[str, Any]) -> dict[str, str] | None:
    for key in ("target_document_name", "document_name"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return {"name": value}
    return None


def success_result(
    tool: str,
    data: Mapping[str, Any],
    duration_ms: float,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Wrap a successful legacy bridge dictionary in tool-schema v1."""
    payload = dict(data)
    result_warnings = list(warnings or [])
    legacy_warning = payload.get("warning")
    if isinstance(legacy_warning, str) and legacy_warning and legacy_warning not in result_warnings:
        result_warnings.append(legacy_warning)
    return {
        "ok": True,
        "tool": tool,
        "bridge_version": BRIDGE_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "profile_id": CAPABILITY_PROFILE_ID,
        "target_document": _target_document(payload),
        "data": payload,
        "warnings": result_warnings,
        "error": None,
        "duration_ms": _duration(duration_ms),
    }


def _error_fields(exc: BaseException) -> tuple[ErrorCode, str, dict[str, Any]]:
    if isinstance(exc, CorelBridgeError):
        return exc.code, str(exc), dict(exc.details)
    if isinstance(exc, (FutureTimeoutError, TimeoutError)):
        return (
            ErrorCode.OPERATION_TIMEOUT,
            "The CorelDRAW operation exceeded the 120-second timeout.",
            {},
        )
    if isinstance(exc, RuntimeError) and "worker" in str(exc).lower():
        return ErrorCode.WORKER_UNAVAILABLE, str(exc), {}
    return (
        ErrorCode.INTERNAL_ERROR,
        "The operator encountered an unexpected internal error.",
        {"exception_type": type(exc).__name__},
    )


def error_result(tool: str, exc: BaseException, duration_ms: float) -> dict[str, Any]:
    """Convert an exception to a stable, non-traceback MCP error envelope."""
    code, message, details = _error_fields(exc)
    return {
        "ok": False,
        "tool": tool,
        "bridge_version": BRIDGE_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "profile_id": CAPABILITY_PROFILE_ID,
        "target_document": None,
        "data": None,
        "warnings": [],
        "error": {
            "code": code.value,
            "message": message,
            "details": details,
        },
        "duration_ms": _duration(duration_ms),
    }
