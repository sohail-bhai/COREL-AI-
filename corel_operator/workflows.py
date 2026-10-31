"""Pure, deterministic planning helpers that do not connect to CorelDRAW."""
from __future__ import annotations

import math
from typing import Any

from .errors import CorelBridgeError, ErrorCode


MAX_LAYOUT_PLACEMENTS = 2000
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
) -> dict[str, Any]:
    """Return a row-major N-up grid, selecting the orientation with greatest capacity.

    Coordinates are measured in inches from the sheet's lower-left corner. The
    item dimensions in each placement reflect any selected 90-degree rotation.
    No CorelDRAW document is read or modified.
    """
    values = {
        "item_width_inches": item_width_inches,
        "item_height_inches": item_height_inches,
        "sheet_width_inches": sheet_width_inches,
        "sheet_height_inches": sheet_height_inches,
        "margin_inches": margin_inches,
        "gutter_inches": gutter_inches,
    }
    for name, raw in values.items():
        try:
            finite = math.isfinite(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else False
        except (OverflowError, TypeError):
            finite = False
        if not finite:
            raise CorelBridgeError(f"{name} must be a finite number.", ErrorCode.INVALID_ARGUMENT)
        if name in ("margin_inches", "gutter_inches"):
            if raw < 0:
                raise CorelBridgeError(f"{name} cannot be negative.", ErrorCode.INVALID_ARGUMENT)
        elif raw <= 0:
            raise CorelBridgeError(f"{name} must be greater than zero.", ErrorCode.INVALID_ARGUMENT)
    if not isinstance(allow_rotate, bool):
        raise CorelBridgeError("allow_rotate must be a boolean.", ErrorCode.INVALID_ARGUMENT)

    usable_width = sheet_width_inches - margin_inches - margin_inches
    usable_height = sheet_height_inches - margin_inches - margin_inches
    if not math.isfinite(usable_width) or not math.isfinite(usable_height):
        raise CorelBridgeError("The dimensions produce non-finite usable sheet bounds.", ErrorCode.INVALID_ARGUMENT)

    def grid(width: float, height: float) -> tuple[int, int, int]:
        def count(usable: float, item: float) -> int:
            if usable <= 0:
                return 0
            numerator = usable + gutter_inches
            denominator = item + gutter_inches
            if not math.isfinite(numerator) or not math.isfinite(denominator):
                raise CorelBridgeError("The dimensions overflow while calculating the layout.", ErrorCode.INVALID_ARGUMENT)
            ratio = numerator / denominator
            if not math.isfinite(ratio):
                raise CorelBridgeError("The dimensions exceed the supported numeric range.", ErrorCode.INVALID_ARGUMENT)
            return max(0, math.floor(ratio))

        columns = count(usable_width, width)
        rows = count(usable_height, height)
        return columns, rows, columns * rows

    normal = grid(item_width_inches, item_height_inches)
    rotated = grid(item_height_inches, item_width_inches) if allow_rotate else (0, 0, 0)
    is_rotated = rotated[2] > normal[2]
    columns, rows, capacity = rotated if is_rotated else normal
    placed_count = min(capacity, MAX_LAYOUT_PLACEMENTS)
    item_width = item_height_inches if is_rotated else item_width_inches
    item_height = item_width_inches if is_rotated else item_height_inches
    placements = [
        {
            "index": index + 1,
            "row": index // columns + 1,
            "column": index % columns + 1,
            "x_inches": round(margin_inches + (index % columns) * (item_width + gutter_inches), 6),
            "y_inches": round(sheet_height_inches - margin_inches - item_height - (index // columns) * (item_height + gutter_inches), 6),
            "width_inches": item_width,
            "height_inches": item_height,
            "rotated": is_rotated,
        }
        for index in range(placed_count)
    ] if columns else []

    result: dict[str, Any] = {
        "fits": capacity > 0,
        "columns": columns,
        "rows": rows,
        "capacity": capacity,
        "rotated": is_rotated,
        "usable_width_inches": round(max(0.0, usable_width), 6),
        "usable_height_inches": round(max(0.0, usable_height), 6),
        "placements": placements,
    }
    if capacity > MAX_LAYOUT_PLACEMENTS:
        result["placements_truncated"] = True
        result["placements_limit"] = MAX_LAYOUT_PLACEMENTS
    return result
