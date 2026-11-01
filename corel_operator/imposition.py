"""Deterministic, guillotine-friendly rectangular sheet imposition."""
from __future__ import annotations

import math
from typing import Any

from .errors import CorelBridgeError, ErrorCode


MAX_LAYOUT_PLACEMENTS = 2000
MAX_MIXED_STRIP_ITERATIONS = 200_000
ROTATION_POLICIES = {"never", "all", "best_fit"}
SHEET_ORIENTATION_POLICIES = {"fixed", "portrait", "landscape", "best_fit"}
GRIPPER_EDGES = {"top", "right", "bottom", "left"}


def _number(name: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CorelBridgeError(f"{name} must be a finite number.", ErrorCode.INVALID_ARGUMENT)
    number = float(value)
    if not math.isfinite(number):
        raise CorelBridgeError(f"{name} must be a finite number.", ErrorCode.INVALID_ARGUMENT)
    if positive and number <= 0:
        raise CorelBridgeError(f"{name} must be greater than zero.", ErrorCode.INVALID_ARGUMENT)
    if not positive and number < 0:
        raise CorelBridgeError(f"{name} cannot be negative.", ErrorCode.INVALID_ARGUMENT)
    return number


def _fit_count(usable: float, item: float, gutter: float) -> int:
    if usable <= 0:
        return 0
    ratio = (usable + gutter) / (item + gutter)
    if not math.isfinite(ratio):
        raise CorelBridgeError(
            "The dimensions exceed the supported numeric range.",
            ErrorCode.INVALID_ARGUMENT,
        )
    # Tolerate only floating-point noise at an exact cut boundary.
    return max(0, math.floor(ratio + 1e-12))


def _waste_ratio(capacity: int, item_width: float, item_height: float, area: float) -> float:
    if area <= 0 or capacity <= 0:
        return 1.0
    try:
        coverage = capacity * item_width * item_height / area
    except OverflowError:
        coverage = 1.0
    return max(0.0, min(1.0, 1.0 - coverage))


def _waste_percent(capacity: int, item_width: float, item_height: float, area: float) -> float:
    return round(_waste_ratio(capacity, item_width, item_height, area) * 100.0, 3)


def _best_mixed_counts(
    available: float,
    first_thickness: float,
    first_value: int,
    second_thickness: float,
    second_value: int,
    gutter: float,
) -> tuple[int, int, int] | None:
    """Solve a two-strip integer packing, requiring both strip types."""
    if first_value <= 0 or second_value <= 0:
        return None
    budget = available + gutter
    first_cost = first_thickness + gutter
    second_cost = second_thickness + gutter
    max_first = math.floor((budget + 1e-12) / first_cost)
    max_second = math.floor((budget + 1e-12) / second_cost)
    if max_first < 1 or max_second < 1:
        return None
    if min(max_first, max_second) > MAX_MIXED_STRIP_ITERATIONS:
        return None

    best: tuple[int, int, int, float] | None = None
    if max_first <= max_second:
        for first in range(1, max_first + 1):
            remaining = budget - first * first_cost
            second = math.floor((remaining + 1e-12) / second_cost)
            if second < 1:
                continue
            value = first * first_value + second * second_value
            unused = max(0.0, remaining - second * second_cost)
            score = (value, -unused, -second)
            if best is None or score > (best[2], -best[3], -best[1]):
                best = (first, second, value, unused)
    else:
        for second in range(1, max_second + 1):
            remaining = budget - second * second_cost
            first = math.floor((remaining + 1e-12) / first_cost)
            if first < 1:
                continue
            value = first * first_value + second * second_value
            unused = max(0.0, remaining - first * first_cost)
            score = (value, -unused, -second)
            if best is None or score > (best[2], -best[3], -best[1]):
                best = (first, second, value, unused)
    return None if best is None else best[:3]


def _orientation_variants(width: float, height: float, policy: str) -> list[tuple[float, float, bool]]:
    supplied = (width, height, False)
    portrait = (min(width, height), max(width, height), width > height)
    landscape = (max(width, height), min(width, height), width < height)
    requested = {
        "fixed": [supplied],
        "portrait": [portrait],
        "landscape": [landscape],
        "best_fit": [supplied, portrait, landscape],
    }[policy]
    variants: list[tuple[float, float, bool]] = []
    seen: set[tuple[float, float]] = set()
    for variant in requested:
        key = variant[:2]
        if key not in seen:
            seen.add(key)
            variants.append(variant)
    return variants


def _candidate_summary(candidate: dict[str, Any], selected: bool = False) -> dict[str, Any]:
    return {
        "layout_strategy": candidate["layout_strategy"],
        "sheet_orientation": candidate["sheet_orientation"],
        "sheet_width_inches": candidate["sheet_width_inches"],
        "sheet_height_inches": candidate["sheet_height_inches"],
        "capacity": candidate["capacity"],
        "waste_percent": candidate["waste_percent"],
        "paper_waste_percent": candidate["paper_waste_percent"],
        "rotation_used": candidate["rotation_used"],
        "mixed_rotation": candidate["mixed_rotation"],
        "cutting_complexity_score": candidate["cutting_complexity_score"],
        "cutting_complexity": candidate["cutting_complexity"],
        "selected": selected,
    }


def _placements(candidate: dict[str, Any], gutter: float) -> list[dict[str, Any]]:
    placements: list[dict[str, Any]] = []
    left = candidate["margins_inches"]["left"]
    top = candidate["margins_inches"]["top"]
    sheet_height = candidate["sheet_height_inches"]
    strategy = candidate["layout_strategy"]

    def add(row: int, column: int, x: float, y: float, width: float, height: float, rotated: bool, strip: int) -> None:
        if len(placements) >= MAX_LAYOUT_PLACEMENTS:
            return
        placements.append({
            "index": len(placements) + 1,
            "row": row,
            "column": column,
            "strip": strip,
            "x_inches": round(x, 6),
            "y_inches": round(y, 6),
            "width_inches": width,
            "height_inches": height,
            "rotated": rotated,
            "rotation_degrees": 90 if rotated else 0,
        })

    item_width = candidate["item_width_inches"]
    item_height = candidate["item_height_inches"]
    if strategy in ("upright_grid", "rotated_grid"):
        rotated = strategy == "rotated_grid"
        width, height = (item_height, item_width) if rotated else (item_width, item_height)
        for row in range(candidate["rows"]):
            y = sheet_height - top - height - row * (height + gutter)
            for column in range(candidate["columns"]):
                add(row + 1, column + 1, left + column * (width + gutter), y, width, height, rotated, row + 1)
                if len(placements) >= MAX_LAYOUT_PLACEMENTS:
                    return placements
        return placements

    if strategy == "mixed_rotated_rows":
        row_number = 0
        cursor_top = sheet_height - top
        for rotated, count in ((False, candidate["upright_strips"]), (True, candidate["rotated_strips"])):
            width, height = (item_height, item_width) if rotated else (item_width, item_height)
            columns = _fit_count(candidate["usable_width_inches"], width, gutter)
            for _ in range(count):
                row_number += 1
                y = cursor_top - height
                for column in range(columns):
                    add(row_number, column + 1, left + column * (width + gutter), y, width, height, rotated, row_number)
                    if len(placements) >= MAX_LAYOUT_PLACEMENTS:
                        return placements
                cursor_top = y - gutter
        return placements

    column_number = 0
    cursor_left = left
    for rotated, count in ((False, candidate["upright_strips"]), (True, candidate["rotated_strips"])):
        width, height = (item_height, item_width) if rotated else (item_width, item_height)
        rows = _fit_count(candidate["usable_height_inches"], height, gutter)
        for _ in range(count):
            column_number += 1
            for row in range(rows):
                y = sheet_height - top - height - row * (height + gutter)
                add(row + 1, column_number, cursor_left, y, width, height, rotated, column_number)
                if len(placements) >= MAX_LAYOUT_PLACEMENTS:
                    return placements
            cursor_left += width + gutter
    return placements


def optimize_sheet_layout(
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
    """Evaluate uniform and mixed-strip N-up candidates without arbitrary nesting.

    ``never`` keeps every item upright, ``all`` rotates every item 90 degrees,
    and ``best_fit`` compares those grids with mixed complete rows and columns.
    """
    item_width = _number("item_width_inches", item_width_inches, positive=True)
    item_height = _number("item_height_inches", item_height_inches, positive=True)
    sheet_width = _number("sheet_width_inches", sheet_width_inches, positive=True)
    sheet_height = _number("sheet_height_inches", sheet_height_inches, positive=True)
    margin = _number("margin_inches", margin_inches)
    gutter = _number("gutter_inches", gutter_inches)
    gripper = _number("gripper_inches", gripper_inches)
    mark_clearance = _number("mark_clearance_inches", mark_clearance_inches)
    if not isinstance(allow_rotate, bool):
        raise CorelBridgeError("allow_rotate must be a boolean.", ErrorCode.INVALID_ARGUMENT)
    legacy_uniform_rotation = rotation_policy is None
    policy = ("best_fit" if allow_rotate else "never") if legacy_uniform_rotation else rotation_policy
    if not isinstance(policy, str) or policy not in ROTATION_POLICIES:
        raise CorelBridgeError("rotation_policy must be one of: never, all, best_fit.", ErrorCode.INVALID_ARGUMENT)
    if not isinstance(sheet_orientation, str) or sheet_orientation not in SHEET_ORIENTATION_POLICIES:
        raise CorelBridgeError("sheet_orientation must be one of: fixed, portrait, landscape, best_fit.", ErrorCode.INVALID_ARGUMENT)
    if not isinstance(gripper_edge, str) or gripper_edge not in GRIPPER_EDGES:
        raise CorelBridgeError("gripper_edge must be one of: top, right, bottom, left.", ErrorCode.INVALID_ARGUMENT)
    if requested_quantity is not None and (
        isinstance(requested_quantity, bool) or not isinstance(requested_quantity, int) or requested_quantity < 1
    ):
        raise CorelBridgeError("requested_quantity must be a positive integer.", ErrorCode.INVALID_ARGUMENT)

    edge_inputs = {
        "left": margin_left_inches,
        "top": margin_top_inches,
        "right": margin_right_inches,
        "bottom": margin_bottom_inches,
    }
    margins: dict[str, float] = {}
    for edge, value in edge_inputs.items():
        margins[edge] = margin if value is None else _number(f"margin_{edge}_inches", value)
        margins[edge] += mark_clearance
    margins[gripper_edge] += gripper
    if any(not math.isfinite(value) for value in margins.values()):
        raise CorelBridgeError(
            "The margin, mark, and gripper allowances exceed the supported numeric range.",
            ErrorCode.INVALID_ARGUMENT,
        )

    candidates: list[dict[str, Any]] = []
    mixed_search_skipped = False
    strategy_rank = {"upright_grid": 0, "rotated_grid": 1, "mixed_rotated_rows": 2, "mixed_rotated_columns": 3}
    for oriented_width, oriented_height, orientation_changed in _orientation_variants(sheet_width, sheet_height, sheet_orientation):
        usable_width = oriented_width - margins["left"] - margins["right"]
        usable_height = oriented_height - margins["top"] - margins["bottom"]
        if not math.isfinite(usable_width) or not math.isfinite(usable_height):
            raise CorelBridgeError(
                "The dimensions produce non-finite usable sheet bounds.",
                ErrorCode.INVALID_ARGUMENT,
            )
        usable_area = max(0.0, usable_width) * max(0.0, usable_height)
        sheet_area = oriented_width * oriented_height
        if not math.isfinite(usable_area) or not math.isfinite(sheet_area):
            raise CorelBridgeError(
                "The dimensions produce sheet areas outside the supported numeric range.",
                ErrorCode.INVALID_ARGUMENT,
            )

        def candidate(strategy: str, columns: int, rows: int, capacity: int, **extra: Any) -> None:
            rotation_used = strategy != "upright_grid"
            mixed = strategy.startswith("mixed_")
            cutting_score = 1 if mixed else 0
            data = {
                "layout_strategy": strategy,
                "sheet_orientation": "portrait" if oriented_height >= oriented_width else "landscape",
                "sheet_orientation_changed": orientation_changed,
                "sheet_width_inches": oriented_width,
                "sheet_height_inches": oriented_height,
                "item_width_inches": item_width,
                "item_height_inches": item_height,
                "usable_width_inches": max(0.0, usable_width),
                "usable_height_inches": max(0.0, usable_height),
                "margins_inches": dict(margins),
                "columns": columns,
                "rows": rows,
                "capacity": capacity,
                "rotation_used": rotation_used,
                "mixed_rotation": mixed,
                "rotated": strategy == "rotated_grid",
                "_waste_ratio": _waste_ratio(capacity, item_width, item_height, usable_area),
                "waste_percent": _waste_percent(capacity, item_width, item_height, usable_area),
                "paper_waste_percent": _waste_percent(capacity, item_width, item_height, sheet_area),
                "cutting_complexity_score": cutting_score,
                "cutting_complexity": "moderate" if mixed else "simple",
                "guillotine_friendly": True,
                **extra,
            }
            candidates.append(data)

        upright_columns = _fit_count(usable_width, item_width, gutter)
        upright_rows = _fit_count(usable_height, item_height, gutter)
        rotated_columns = _fit_count(usable_width, item_height, gutter)
        rotated_rows = _fit_count(usable_height, item_width, gutter)
        if policy in ("never", "best_fit"):
            candidate("upright_grid", upright_columns, upright_rows, upright_columns * upright_rows)
        if policy in ("all", "best_fit"):
            candidate("rotated_grid", rotated_columns, rotated_rows, rotated_columns * rotated_rows)
        if policy == "best_fit" and not legacy_uniform_rotation and item_width != item_height:
            row_mix = _best_mixed_counts(usable_height, item_height, upright_columns, item_width, rotated_columns, gutter)
            if row_mix:
                upright_count, rotated_count, capacity = row_mix
                candidate(
                    "mixed_rotated_rows", max(upright_columns, rotated_columns), upright_count + rotated_count, capacity,
                    upright_strips=upright_count, rotated_strips=rotated_count,
                )
            elif min(upright_rows, rotated_rows) > MAX_MIXED_STRIP_ITERATIONS:
                mixed_search_skipped = True
            column_mix = _best_mixed_counts(usable_width, item_width, upright_rows, item_height, rotated_rows, gutter)
            if column_mix:
                upright_count, rotated_count, capacity = column_mix
                candidate(
                    "mixed_rotated_columns", upright_count + rotated_count, max(upright_rows, rotated_rows), capacity,
                    upright_strips=upright_count, rotated_strips=rotated_count,
                )
            elif min(upright_columns, rotated_columns) > MAX_MIXED_STRIP_ITERATIONS:
                mixed_search_skipped = True

    if mixed_search_skipped:
        raise CorelBridgeError(
            "Exact mixed-rotation search exceeds the supported 200,000 strips; use larger units or a uniform rotation policy.",
            ErrorCode.INVALID_ARGUMENT,
        )

    def rank(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            -item["capacity"], item["_waste_ratio"], item["cutting_complexity_score"],
            item["sheet_orientation_changed"], strategy_rank[item["layout_strategy"]],
        )

    candidates.sort(key=rank)
    selected = candidates[0]
    placements = _placements(selected, gutter)
    capacity = selected["capacity"]
    result = {
        "fits": capacity > 0,
        "rotation_policy": policy,
        "mixed_rotation_evaluated": policy == "best_fit" and not legacy_uniform_rotation,
        "sheet_orientation_policy": sheet_orientation,
        "layout_strategy": selected["layout_strategy"],
        "sheet_orientation": selected["sheet_orientation"],
        "sheet_orientation_changed": selected["sheet_orientation_changed"],
        "sheet_width_inches": selected["sheet_width_inches"],
        "sheet_height_inches": selected["sheet_height_inches"],
        "columns": selected["columns"],
        "rows": selected["rows"],
        "capacity": capacity,
        "copies_per_sheet": capacity,
        "rotated": selected["rotated"],
        "rotation_used": selected["rotation_used"],
        "mixed_rotation": selected["mixed_rotation"],
        "usable_width_inches": round(selected["usable_width_inches"], 6),
        "usable_height_inches": round(selected["usable_height_inches"], 6),
        "margins_inches": {key: round(value, 6) for key, value in margins.items()},
        "gripper_inches": gripper,
        "gripper_edge": gripper_edge,
        "mark_clearance_inches": mark_clearance,
        "waste_percent": selected["waste_percent"],
        "paper_waste_percent": selected["paper_waste_percent"],
        "cutting_complexity_score": selected["cutting_complexity_score"],
        "cutting_complexity": selected["cutting_complexity"],
        "guillotine_friendly": True,
        "scale_percent": 100.0,
        "placements": placements,
        "alternatives": [_candidate_summary(item, item is selected) for item in candidates],
    }
    if capacity > MAX_LAYOUT_PLACEMENTS:
        result["placements_truncated"] = True
        result["placements_limit"] = MAX_LAYOUT_PLACEMENTS
    if requested_quantity is not None:
        sheets = math.ceil(requested_quantity / capacity) if capacity else 0
        total = sheets * capacity
        result.update({
            "requested_quantity": requested_quantity,
            "sheets_required": sheets,
            "total_produced": total,
            "overage": total - requested_quantity if capacity else 0,
        })
    return result
