"""Pure input validation for focused, bounded object inspection."""
from __future__ import annotations

from .errors import CorelBridgeError, ErrorCode


MAX_NAME_CHARS = 256
MAX_NAME_SCAN = 10000
DEFAULT_TEXT_CHARS = 2000
MAX_TEXT_CHARS = 10000


def validate_inspection_selector(object_name: str, shape_index: int) -> None:
    if not isinstance(object_name, str) or len(object_name) > MAX_NAME_CHARS:
        raise CorelBridgeError(
            "object_name must be a string of at most 256 characters.",
            ErrorCode.INVALID_ARGUMENT,
        )
    if object_name and not object_name.strip():
        raise CorelBridgeError("object_name cannot be whitespace only.", ErrorCode.INVALID_ARGUMENT)
    if type(shape_index) is not int or shape_index < 0:
        raise CorelBridgeError(
            "shape_index must be a nonnegative integer.", ErrorCode.INVALID_ARGUMENT,
        )
    if bool(object_name) == (shape_index > 0):
        raise CorelBridgeError(
            "Specify exactly one selector: object_name OR shape_index.",
            ErrorCode.AMBIGUOUS_SELECTOR,
        )


def validate_text_limit(max_text_chars: int) -> None:
    if type(max_text_chars) is not int or not 0 <= max_text_chars <= MAX_TEXT_CHARS:
        raise CorelBridgeError(
            "max_text_chars must be an integer from 0 through 10000.",
            ErrorCode.INVALID_ARGUMENT,
        )
