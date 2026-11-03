"""Worker classification and bounded metadata; no COM access or automatic retry."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .errors import CorelBridgeError, ErrorCode

READ_ONLY_METHODS = frozenset({
    "connect", "status", "list_open_documents", "get_document_info", "list_pages",
    "get_page_bounds", "list_layers", "list_objects", "find_objects",
    "get_object_info", "get_object_bounds", "get_text_properties", "get_fill",
    "inspect_repeat_unit", "list_fonts", "get_object_transform", "inspect_text_template", "get_curve_geometry", "get_transparency",
})
SAFE_REFUSALS = frozenset({
    ErrorCode.NO_TARGET_DOCUMENT, ErrorCode.CONFIRMATION_REQUIRED,
    ErrorCode.INVALID_ARGUMENT, ErrorCode.OBJECT_NOT_FOUND, ErrorCode.AMBIGUOUS_SELECTOR,
    ErrorCode.UNSUPPORTED_IN_PROFILE, ErrorCode.UNSAFE_PATH, ErrorCode.OUTPUT_EXISTS,
})
MAX_OPERATION_HISTORY = 64
_OPERATION_ID = re.compile(r"[0-9a-f]{32}\Z")


def validate_operation_id(value: Any) -> None:
    if type(value) is not str or not _OPERATION_ID.fullmatch(value):
        raise CorelBridgeError("operation_id must be a 32-character lowercase UUID hex value.", ErrorCode.INVALID_ARGUMENT)


def validate_recovery_probe(value: Any) -> None:
    fields = {"connected", "target_bound", "document_session_id", "open_document_count",
              "page_index", "page_object_count", "unit_code", "reference_point_code", "dirty"}
    valid = type(value) is dict and set(value) == fields
    if valid:
        valid = (type(value["connected"]) is bool and type(value["target_bound"]) is bool
                 and type(value["open_document_count"]) is int and 0 <= value["open_document_count"] <= 1000)
    if valid and value["target_bound"]:
        valid = (value["connected"] and type(value["document_session_id"]) is str
                 and re.fullmatch(r"doc-[0-9]{4,16}", value["document_session_id"]) is not None
                 and type(value["dirty"]) is bool)
        for field, minimum in (("page_index", 1), ("page_object_count", 0), ("unit_code", 0), ("reference_point_code", 0)):
            valid = valid and type(value[field]) is int and minimum <= value[field] <= 2147483647
    elif valid:
        valid = all(value[field] is None for field in ("document_session_id", "page_index", "page_object_count", "unit_code", "reference_point_code", "dirty"))
        if not value["connected"]:
            valid = valid and value["open_document_count"] == 0
    if not valid:
        raise CorelBridgeError("Could not verify a complete document reconciliation result.", ErrorCode.COREL_COM_ERROR)


def native_busy(exc: BaseException) -> bool:
    """Recognize documented COM busy/rejected HRESULTs without exposing messages."""
    seen = set()
    for _ in range(8):
        if id(exc) in seen:
            break
        seen.add(id(exc))
        try:
            hresult = getattr(exc, "hresult", None)
        except Exception:
            hresult = None
        if type(hresult) is int and (hresult & 0xFFFFFFFF) in (0x80010001, 0x8001010A, 0x8001010B):
            return True
        cause = exc.__cause__ or exc.__context__
        if cause is None:
            break
        exc = cause
    return False


def failure_recovery_reason(exc: BaseException, mutation: bool, mutation_started: Any = None) -> str | None:
    details = exc.details if isinstance(exc, CorelBridgeError) else {}
    nested = details.get("rollback") if type(details) is dict else None
    if details.get("rollback_verified") is True or (type(nested) is dict and nested.get("verified") is True):
        return None
    if "rollback_verified" in details or type(nested) is dict:
        return "rollback_unverified"
    if (not mutation or mutation_started is False) and isinstance(exc, CorelBridgeError) and exc.code in SAFE_REFUSALS:
        return None
    if native_busy(exc):
        return "application_busy"
    return "mutation_failed" if mutation else "read_failed"


@dataclass
class DispatchJob:
    operation_id: str
    method: str
    args: tuple
    kwargs: dict
    future: Any
    record: Any
    mutation: bool
    submitted: float
    submitted_utc: str
    started: bool = False
    timed_out: bool = False
    reconciliation: bool = False
    recovery_operation_id: str | None = None
    acknowledge_partial_changes: bool = False
