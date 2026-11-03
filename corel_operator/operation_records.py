"""Opt-in, bounded operation events containing metadata only.

No input/output content, paths, names, exception text, or arbitrary dictionary
keys enter the journal. Each process creates exclusive files outside the repo.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import CorelBridgeError, ErrorCode
from .version import BRIDGE_VERSION, CAPABILITY_PROFILE_ID

MAX_SEGMENT_BYTES = 2 * 1024 * 1024
MAX_SEGMENTS = 8
MAX_ID_SCAN = 256
_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_DOCUMENT = re.compile(r"doc-[0-9]{4,16}\Z")
_OBJECT = re.compile(r"doc-[0-9]{4,16}:shape:[0-9]{1,10}\Z")
_TOOL = re.compile(r"[a-z][a-z0-9_]{0,79}\Z")
_EVENTS = {"requested", "worker_started", "worker_completed", "worker_failed", "worker_cancelled", "returned"}


def input_summary(args: tuple, kwargs: dict) -> dict:
    """Only top-level type counts; never inspect strings or nested client data."""
    counts = {key: 0 for key in ("string", "number", "boolean", "array", "object", "null", "other")}
    for value in (*args, *kwargs.values()):
        if value is None:
            key = "null"
        elif type(value) is bool:
            key = "boolean"
        elif type(value) in (int, float):
            key = "number"
        elif type(value) is str:
            key = "string"
        elif type(value) in (list, tuple):
            key = "array"
        elif type(value) is dict:
            key = "object"
        else:
            key = "other"
        counts[key] += 1
    return {"parameter_count": sum(counts.values()), "type_counts": counts}


def target_ids(bridge: Any) -> dict:
    """Snapshot already-known state on the COM worker without any native reads."""
    result = {}
    state = vars(bridge)
    session = state.get("_bridge_session_id")
    if type(session) is str and _HEX32.fullmatch(session):
        result["bridge_session_id"] = session
    document_key = state.get("_target_document_key")
    document_sessions = state.get("_document_sessions", {})
    if type(document_sessions) is dict and type(document_key) is str:
        document_session = document_sessions.get(document_key)
        if type(document_session) is str and _DOCUMENT.fullmatch(document_session):
            result["document_session_id"] = document_session
    return result


def exception_code(exc: BaseException) -> str:
    if isinstance(exc, CorelBridgeError) and isinstance(exc.code, ErrorCode):
        return exc.code.value
    if isinstance(exc, TimeoutError):
        return ErrorCode.OPERATION_TIMEOUT.value
    if isinstance(exc, RuntimeError) and "worker" in str(exc).lower():
        return ErrorCode.WORKER_UNAVAILABLE.value
    return ErrorCode.INTERNAL_ERROR.value


def result_metadata(data: Any = None, error: BaseException | None = None) -> dict:
    """Extract only allowlisted booleans and native IDs with bounded work."""
    result = {"result_code": exception_code(error) if error is not None else "OK"}
    payload = data if type(data) is dict else {}
    details = error.details if isinstance(error, CorelBridgeError) else payload
    rollback = {}
    for key in ("rollback_attempted", "rollback_verified", "rollback_succeeded", "recovery_incomplete"):
        value = details.get(key) if type(details) is dict else None
        if type(value) is bool:
            rollback[key] = value
    nested = details.get("rollback") if type(details) is dict else None
    if type(nested) is dict:
        for source, destination in (("attempted", "rollback_attempted"), ("verified", "rollback_verified"), ("undo_succeeded", "rollback_succeeded")):
            if destination not in rollback and type(nested.get(source)) is bool:
                rollback[destination] = nested[source]
    result["rollback"] = rollback
    created = any(payload.get(key) is True for key in ("created", "duplicated", "imported", "grouped", "prepared", "executed"))
    result["created_object_ids"] = []
    result["created_ids_available"] = False
    if not created:
        return result
    seen = set()
    scanned = 0
    limited = False

    def walk(value, depth=0):
        nonlocal scanned, limited
        if scanned >= MAX_ID_SCAN or depth > 5:
            limited = True
            return
        scanned += 1
        if type(value) is list:
            for item in value[:MAX_ID_SCAN]:
                walk(item, depth + 1)
        elif type(value) is dict:
            static_id = value.get("static_id")
            if type(static_id) is int and 0 <= static_id <= 2147483647:
                seen.add(("static_id", static_id))
            object_id = value.get("object_id")
            if type(object_id) is str and _OBJECT.fullmatch(object_id):
                seen.add(("object_id", object_id))
            for key in ("object", "objects", "object_reference", "created_objects", "elements", "result"):
                if key in value:
                    walk(value[key], depth + 1)
    walk(payload)
    result["created_object_ids"] = [{key: value} for key, value in sorted(seen, key=lambda item: (item[0], str(item[1])))]
    result["created_ids_available"] = bool(seen)
    result["created_ids_scan_limited"] = limited or scanned >= MAX_ID_SCAN
    return result


def safe_metadata(metadata: dict) -> dict:
    """Enforce redaction again at the final disk boundary, including internal misuse."""
    result = {}
    summary = metadata.get("input_summary")
    if type(summary) is dict and type(summary.get("type_counts")) is dict:
        counts = {}
        for key in ("string", "number", "boolean", "array", "object", "null", "other"):
            value = summary["type_counts"].get(key)
            if type(value) is int and 0 <= value <= 10000:
                counts[key] = value
        result["input_summary"] = {"type_counts": counts, "parameter_count": sum(counts.values())}
    targets = metadata.get("target_ids")
    if type(targets) is dict:
        result["target_ids"] = {}
        for key, pattern in (("bridge_session_id", _HEX32), ("document_session_id", _DOCUMENT)):
            value = targets.get(key)
            if type(value) is str and pattern.fullmatch(value):
                result["target_ids"][key] = value
    code = metadata.get("result_code")
    if type(code) is str and code in {"OK", *(code.value for code in ErrorCode)}:
        result["result_code"] = code
    if type(metadata.get("created_object_ids")) is list:
        ids = []
        for item in metadata["created_object_ids"][:MAX_ID_SCAN]:
            if type(item) is not dict:
                continue
            value = item.get("static_id")
            if type(value) is int and 0 <= value <= 2147483647:
                ids.append({"static_id": value})
            value = item.get("object_id")
            if type(value) is str and _OBJECT.fullmatch(value):
                ids.append({"object_id": value})
        result["created_object_ids"] = ids[:MAX_ID_SCAN]
        result["created_ids_available"] = bool(ids)
    for key in ("created_ids_scan_limited",):
        if type(metadata.get(key)) is bool:
            result[key] = metadata[key]
    rollback = metadata.get("rollback")
    if type(rollback) is dict:
        result["rollback"] = {
            key: rollback[key] for key in ("rollback_attempted", "rollback_verified", "rollback_succeeded", "recovery_incomplete")
            if type(rollback.get(key)) is bool
        }
    duration = metadata.get("duration_ms")
    if type(duration) in (float, int) and math.isfinite(duration):
        result["duration_ms"] = round(max(0., duration), 3)
    return result


class OperationJournal:
    def __init__(self, directory: str | Path | None = None, repository_root: Path | None = None):
        self.enabled = directory is not None
        self.available = True
        self.events_written = 0
        self._directory = Path(directory) if directory is not None else None
        self._repository_root = (repository_root or Path(__file__).resolve().parents[1]).resolve()
        self._file = None
        self._bytes = 0
        self._segment = 0
        self._session = uuid.uuid4().hex
        self._lock = threading.Lock()
        if self.enabled:
            try:
                self._validate_directory()
            except Exception:
                self.available = False

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("COREL_OPERATION_LOG_DIR") or None)

    def _validate_directory(self) -> Path:
        if self._directory is None or not self._directory.is_absolute():
            raise ValueError("Operation journal requires an absolute directory")
        resolved = self._directory.resolve()
        if resolved == self._repository_root or self._repository_root in resolved.parents:
            raise ValueError("Operation journal must be outside the repository")
        return resolved

    def _open_segment(self):
        if self._segment >= MAX_SEGMENTS:
            raise ValueError("Operation journal session capacity exhausted")
        directory = self._validate_directory()
        directory.mkdir(parents=True, exist_ok=True)
        # Resolve again after creation to reject a newly introduced junction/symlink.
        directory = self._validate_directory()
        self._segment += 1
        path = directory / f"operations-{self._session}-{self._segment:04d}.jsonl"
        self._file = path.open("xb")
        self._bytes = 0

    def write(self, operation_id: str, tool: str, event: str, **metadata) -> bool:
        if not self.enabled:
            return False
        with self._lock:
            if not self.available:
                return False
            try:
                if not _HEX32.fullmatch(operation_id) or not _TOOL.fullmatch(tool) or event not in _EVENTS:
                    raise ValueError("Invalid internal operation metadata")
                record = {
                    "schema_version": 1, "operation_id": operation_id,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "tool": tool, "profile_id": CAPABILITY_PROFILE_ID,
                    "bridge_version": BRIDGE_VERSION, "event": event,
                }
                record.update(safe_metadata(metadata))
                encoded = (json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")
                if len(encoded) > min(32768, MAX_SEGMENT_BYTES):
                    raise ValueError("Operation metadata exceeds event limit")
                if self._file is None:
                    self._open_segment()
                elif self._bytes + len(encoded) > MAX_SEGMENT_BYTES:
                    self._file.close(); self._file = None
                    self._open_segment()
                self._file.write(encoded)
                self._file.flush()
                os.fsync(self._file.fileno())
                self._bytes += len(encoded)
                self.events_written += 1
                return True
            except Exception:
                self.available = False
                if self._file is not None:
                    try:
                        self._file.close()
                    except Exception:
                        pass
                    self._file = None
                return False

    def close(self):
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None


@dataclass(frozen=True)
class RecordedOperation:
    operation_id: str
    tool: str
    journal: OperationJournal


current_operation: ContextVar[RecordedOperation | None] = ContextVar("corel_recorded_operation", default=None)
