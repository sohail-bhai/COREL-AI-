"""Bounded, serializable selectors issued by one bridge process.

References contain opaque identities and a signature, never COM proxies. Indices
are diagnostic snapshots; resolution must use identity and establish uniqueness.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from .errors import CorelBridgeError, ErrorCode

MAX_REFERENCE_DEPTH = 32
MAX_REFERENCE_SCAN = 10000
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SESSION = re.compile(r"[0-9a-f]{32}\Z")
_FIELDS = {
    "version", "bridge_session_id", "document_session_id", "page_identity",
    "layer_identity", "ancestor_identities", "shape_identity", "static_id",
    "object_name", "shape_type_code", "page_index", "layer_index", "shape_path",
    "signature",
}


def validate_reference_selector(
    object_name: str, shape_index: int, object_reference: Any,
) -> None:
    """Reject conflicting or malformed references before touching CorelDRAW."""
    if object_reference is None:
        return
    if type(object_name) is not str or type(shape_index) is not int:
        raise CorelBridgeError("Invalid object selector types.", ErrorCode.INVALID_ARGUMENT)
    if object_name != "" or shape_index != 0:
        raise CorelBridgeError(
            "Supply object_reference alone, without a name or index.",
            ErrorCode.AMBIGUOUS_SELECTOR,
        )
    validate_reference(object_reference)


def validate_reference(value: Any) -> None:
    def invalid() -> None:
        raise CorelBridgeError("Malformed object_reference.", ErrorCode.INVALID_ARGUMENT)

    if type(value) is not dict or set(value) != _FIELDS:
        invalid()
    if type(value["version"]) is not int or value["version"] != 1:
        invalid()
    if type(value["bridge_session_id"]) is not str or not _SESSION.fullmatch(value["bridge_session_id"]):
        invalid()
    session = value["document_session_id"]
    if type(session) is not str or not re.fullmatch(r"doc-[0-9]{4,16}", session):
        invalid()
    for field in ("page_identity", "layer_identity", "shape_identity", "signature"):
        if type(value[field]) is not str or not _HEX.fullmatch(value[field]):
            invalid()
    ancestors = value["ancestor_identities"]
    if type(ancestors) is not list or len(ancestors) > MAX_REFERENCE_DEPTH:
        invalid()
    if any(type(item) is not str or not _HEX.fullmatch(item) for item in ancestors):
        invalid()
    for field, minimum in (("static_id", 0), ("shape_type_code", 0), ("page_index", 1), ("layer_index", 1)):
        if type(value[field]) is not int or not minimum <= value[field] <= 2147483647:
            invalid()
    if type(value["object_name"]) is not str or len(value["object_name"]) > 256:
        invalid()
    path = value["shape_path"]
    if type(path) is not list or len(path) != len(ancestors) + 1:
        invalid()
    if any(type(index) is not int or not 1 <= index <= 2147483647 for index in path):
        invalid()


def identity_token(secret: bytes, identity: str) -> str:
    return hmac.new(secret, identity.encode("utf-8"), hashlib.sha256).hexdigest()


def reference_signature(secret: bytes, value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "signature"}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret, encoded, hashlib.sha256).hexdigest()


def authenticate_reference(secret: bytes, session_id: str, value: dict[str, Any]) -> None:
    if value["bridge_session_id"] != session_id:
        raise CorelBridgeError(
            "object_reference belongs to another bridge session; inspect the document again.",
            ErrorCode.OBJECT_NOT_FOUND,
        )
    if not hmac.compare_digest(reference_signature(secret, value), value["signature"]):
        raise CorelBridgeError("object_reference was altered or was not issued by this bridge.", ErrorCode.INVALID_ARGUMENT)
