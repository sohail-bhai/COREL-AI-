"""Pure, deterministic planning helpers that do not connect to CorelDRAW."""
from __future__ import annotations

from typing import Any

from .errors import CorelBridgeError, ErrorCode
from .imposition import MAX_LAYOUT_PLACEMENTS, optimize_sheet_layout


MAX_CHEST_NUMBER_SEQUENCE = 1000


def build_chest_number_sequence(
    start: int,
    end: int,
    zero_pad_width: int = 0,
    item_width_inches: float | None = None,
    item_height_inches: float | None = None,
    sheet_width_inches: float | None = None,
    sheet_height_inches: float | None = None,
    margin_inches: float = 0.0,
    gutter_inches: float = 0.0,
    allow_rotate: bool = True,
) -> dict[str, Any]:
    """Build and optionally lay out a bounded sequence before any document mutation."""
    for name, value in (("start", start), ("end", end), ("zero_pad_width", zero_pad_width)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise CorelBridgeError(f"{name} must be an integer.", ErrorCode.INVALID_ARGUMENT)
    if start < 0 or end < start:
        raise CorelBridgeError("The sequence must have a nonnegative start and end at or after start.", ErrorCode.INVALID_ARGUMENT)
    if not 0 <= zero_pad_width <= 12:
        raise CorelBridgeError("zero_pad_width must be between 0 and 12.", ErrorCode.INVALID_ARGUMENT)
    count = end - start + 1
    if count > MAX_CHEST_NUMBER_SEQUENCE:
        raise CorelBridgeError(
            f"A single batch cannot exceed {MAX_CHEST_NUMBER_SEQUENCE} numbers.",
            ErrorCode.INVALID_ARGUMENT,
            {"requested_count": count, "maximum_count": MAX_CHEST_NUMBER_SEQUENCE},
        )

    layout_inputs = (
        item_width_inches,
        item_height_inches,
        sheet_width_inches,
        sheet_height_inches,
    )
    has_layout = [value is not None for value in layout_inputs]
    if any(has_layout) and not all(has_layout):
        raise CorelBridgeError(
            "Provide item width, item height, sheet width, and sheet height together to calculate a layout.",
            ErrorCode.INVALID_ARGUMENT,
        )
    if not any(has_layout) and (margin_inches != 0 or gutter_inches != 0 or allow_rotate is not True):
        raise CorelBridgeError(
            "Margin, gutter, and rotation options require all four item and sheet dimensions.",
            ErrorCode.INVALID_ARGUMENT,
        )

    layout = None
    if all(has_layout):
        layout = calculate_sheet_layout(
            item_width_inches, item_height_inches, sheet_width_inches,
            sheet_height_inches, margin_inches, gutter_inches, allow_rotate,
        )

    items = [
        {"value": number, "label": str(number).zfill(zero_pad_width), "object_name": f"chest_number_{number:0{zero_pad_width}d}" if zero_pad_width else f"chest_number_{number}"}
        for number in range(start, end + 1)
    ]
    fits_sheet = layout is not None and layout["capacity"] >= count
    if layout is not None and fits_sheet:
        for item, placement in zip(items, layout["placements"]):
            item["placement"] = placement
    return {
        "count": count,
        "sequence_validation": {"missing": [], "duplicates": []},
        "sequence_valid": True,
        "layout_checked": layout is not None,
        "fits_sheet": fits_sheet,
        "layout": layout,
        "items": items,
    }


def calculate_sheet_layout(
    item_width_inches: float,
    item_height_inches: float,
    sheet_width_inches: float,
    sheet_height_inches: float,
    margin_inches: float = 0.0,
    gutter_inches: float = 0.0,
    allow_rotate: bool = True,
    rotation_policy: str | None = None,
    sheet_orientation: str = "fixed",
    margin_left_inches: float | None = None,
    margin_top_inches: float | None = None,
    margin_right_inches: float | None = None,
    margin_bottom_inches: float | None = None,
    gripper_inches: float = 0.0,
    gripper_edge: str = "bottom",
    mark_clearance_inches: float = 0.0,
    requested_quantity: int | None = None,
) -> dict[str, Any]:
    """Return an exact, guillotine-friendly N-up sheet layout.

    Coordinates are measured in inches from the sheet's lower-left corner. The
    optimizer evaluates upright, fully rotated, mixed-row, mixed-column, and
    requested sheet-orientation candidates. No CorelDRAW document is modified.
    """
    return optimize_sheet_layout(
        item_width_inches, item_height_inches, sheet_width_inches, sheet_height_inches,
        margin_inches, gutter_inches, allow_rotate, rotation_policy, sheet_orientation,
        margin_left_inches, margin_top_inches, margin_right_inches, margin_bottom_inches,
        gripper_inches, gripper_edge, mark_clearance_inches, requested_quantity,
    )
