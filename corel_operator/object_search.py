"""Pure, bounded input validation for object inspection; no COM dependency."""
from __future__ import annotations

from .errors import CorelBridgeError, ErrorCode


def validate_search_inputs(
    name_contains: str, shape_type_code: int | None, text_contains: str,
    page_index: int | None, layer_name: str, max_results: int,
    include_nested: bool, case_sensitive: bool, max_depth: int, max_scan: int,
) -> None:
    for key, value, limit in (
        ("name_contains", name_contains, 256),
        ("text_contains", text_contains, 1024),
        ("layer_name", layer_name, 256),
    ):
        if not isinstance(value, str) or len(value) > limit:
            raise CorelBridgeError(
                f"{key} must be a string of at most {limit} characters.",
                ErrorCode.INVALID_ARGUMENT,
            )
    for key, value, minimum, maximum in (
        ("max_results", max_results, 1, 1000),
        ("max_depth", max_depth, 0, 16),
        ("max_scan", max_scan, 1, 10000),
    ):
        if type(value) is not int or not minimum <= value <= maximum:
            raise CorelBridgeError(
                f"{key} must be an integer from {minimum} to {maximum}.",
                ErrorCode.INVALID_ARGUMENT,
            )
    for key, value, minimum in (
        ("shape_type_code", shape_type_code, 0), ("page_index", page_index, 1),
    ):
        if value is not None and (type(value) is not int or value < minimum):
            raise CorelBridgeError(
                f"{key} must be null or an integer of at least {minimum}.",
                ErrorCode.INVALID_ARGUMENT,
            )
    for key, value in (("include_nested", include_nested), ("case_sensitive", case_sensitive)):
        if type(value) is not bool:
            raise CorelBridgeError(f"{key} must be a boolean.", ErrorCode.INVALID_ARGUMENT)
