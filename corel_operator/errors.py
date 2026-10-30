"""Stable operator error codes and exceptions."""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class ErrorCode(str, Enum):
    NO_TARGET_DOCUMENT = "NO_TARGET_DOCUMENT"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
    AMBIGUOUS_SELECTOR = "AMBIGUOUS_SELECTOR"
    UNSUPPORTED_IN_PROFILE = "UNSUPPORTED_IN_PROFILE"
    UNSAFE_PATH = "UNSAFE_PATH"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    COREL_COM_ERROR = "COREL_COM_ERROR"
    OPERATION_TIMEOUT = "OPERATION_TIMEOUT"
    WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class CorelBridgeError(RuntimeError):
    """An expected bridge failure that is safe to return to an MCP client."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.COREL_COM_ERROR,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})
