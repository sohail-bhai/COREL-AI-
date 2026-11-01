"""Deterministic paired-row nesting for non-rectangular vector dielines."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable

from .errors import CorelBridgeError, ErrorCode
from .workflows import calculate_sheet_layout


Point = tuple[float, float]
Polygon = list[Point]
MAX_CONTOUR_POINTS = 5000
MAX_CONTOUR_COLUMNS = 500
MAX_CONTOUR_ROWS = 2000
MAX_CONTOUR_QUANTITY = 5000
MAX_CONTOUR_PLACEMENTS = MAX_CONTOUR_QUANTITY
CUTTING_METHODS = {"unknown", "digital_cutter", "die_cut", "guillotine"}
FOOTPRINT_KINDS = {"auto", "rectangular", "contour"}
SHEET_ORIENTATIONS = {"fixed", "portrait", "landscape", "best_fit"}
EPSILON = 1e-9


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


def _coordinate(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CorelBridgeError(f"{name} must be a finite number.", ErrorCode.INVALID_ARGUMENT)
    number = float(value)
    if not math.isfinite(number):
        raise CorelBridgeError(f"{name} must be a finite number.", ErrorCode.INVALID_ARGUMENT)
    return number


def classify_imposition_job(
    footprint_kind: str = "auto",
    has_explicit_cut_contour: bool = False,
    cutting_method: str = "unknown",
    allow_180_rotation: bool | None = None,
    source_is_combined: bool = False,
) -> dict[str, Any]:
    """Route obvious rectangles silently and ask production questions only for contours."""
    if footprint_kind not in FOOTPRINT_KINDS:
        raise CorelBridgeError("footprint_kind must be auto, rectangular, or contour.", ErrorCode.INVALID_ARGUMENT)
    if cutting_method not in CUTTING_METHODS:
        raise CorelBridgeError(
            "cutting_method must be unknown, digital_cutter, die_cut, or guillotine.",
            ErrorCode.INVALID_ARGUMENT,
        )
    for name, value in (
        ("has_explicit_cut_contour", has_explicit_cut_contour),
        ("source_is_combined", source_is_combined),
    ):
        if not isinstance(value, bool):
            raise CorelBridgeError(f"{name} must be a boolean.", ErrorCode.INVALID_ARGUMENT)
    if allow_180_rotation is not None and not isinstance(allow_180_rotation, bool):
        raise CorelBridgeError("allow_180_rotation must be a boolean or null.", ErrorCode.INVALID_ARGUMENT)

    blocking: list[dict[str, str]] = []
    questions: list[dict[str, Any]] = []
    if source_is_combined:
        blocking.append({
            "code": "COMBINED_SOURCE_NOT_REPEAT_UNIT",
            "message": "Provide one independently grouped repeat unit, not an already imposed multi-copy image or group.",
        })

    contour_job = footprint_kind == "contour" or (footprint_kind == "auto" and has_explicit_cut_contour)
    if not contour_job:
        return {
            "workflow": "rectangular_n_up",
            "requires_clarification": False,
            "ready": not blocking,
            "questions": [],
            "blocking_issues": blocking,
            "reason": "The footprint is rectangular; cutter details do not affect rectangular N-up geometry.",
        }

    if not has_explicit_cut_contour:
        questions.append({
            "id": "cut_contour",
            "question": "Which closed vector object is the actual cut contour/dieline?",
            "required": True,
        })
    if cutting_method == "unknown":
        questions.append({
            "id": "cutting_method",
            "question": "How will this non-rectangular job be cut?",
            "options": ["digital_cutter", "die_cut", "guillotine"],
            "required": True,
        })
    if cutting_method in {"digital_cutter", "die_cut"} and allow_180_rotation is None:
        questions.append({
            "id": "allow_180_rotation",
            "question": "May complete repeat units rotate 180 degrees, considering grain and design direction?",
            "options": [True, False],
            "required": True,
        })

    workflow = "rectangular_n_up" if cutting_method == "guillotine" else "contour_nesting"
    reason = (
        "Guillotine-only cutting requires rectangular separation bounds."
        if cutting_method == "guillotine"
        else "The non-rectangular contour may permit safe paired-row interlocking."
    )
    return {
        "workflow": workflow,
        "requires_clarification": bool(questions),
        "ready": not blocking and not questions,
        "questions": questions,
        "blocking_issues": blocking,
        "reason": reason,
    }


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    return (
        abs(_cross(start, end, point)) <= EPSILON
        and min(start[0], end[0]) - EPSILON <= point[0] <= max(start[0], end[0]) + EPSILON
        and min(start[1], end[1]) - EPSILON <= point[1] <= max(start[1], end[1]) + EPSILON
    )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point, *, proper_only: bool = False) -> bool:
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    proper = ((ab_c > EPSILON and ab_d < -EPSILON) or (ab_c < -EPSILON and ab_d > EPSILON)) and (
        (cd_a > EPSILON and cd_b < -EPSILON) or (cd_a < -EPSILON and cd_b > EPSILON)
    )
    if proper or proper_only:
        return proper
    return any((
        abs(ab_c) <= EPSILON and _point_on_segment(c, a, b),
        abs(ab_d) <= EPSILON and _point_on_segment(d, a, b),
        abs(cd_a) <= EPSILON and _point_on_segment(a, c, d),
        abs(cd_b) <= EPSILON and _point_on_segment(b, c, d),
    ))


def _edges(points: Polygon) -> Iterable[tuple[Point, Point]]:
    for index, point in enumerate(points):
        yield point, points[(index + 1) % len(points)]


def _polygon_area(points: Polygon) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in _edges(points))) / 2.0


def _point_location(point: Point, polygon: Polygon) -> int:
    """Return -1 outside, 0 on boundary, or 1 strictly inside."""
    inside = False
    for start, end in _edges(polygon):
        if _point_on_segment(point, start, end):
            return 0
        if (start[1] > point[1]) != (end[1] > point[1]):
            x_at_y = start[0] + (point[1] - start[1]) * (end[0] - start[0]) / (end[1] - start[1])
            if x_at_y > point[0]:
                inside = not inside
    return 1 if inside else -1


def _distance_point_segment(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= EPSILON:
        return math.dist(point, start)
    ratio = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    projection = (start[0] + ratio * dx, start[1] + ratio * dy)
    return math.dist(point, projection)


def _segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(
        _distance_point_segment(a, c, d),
        _distance_point_segment(b, c, d),
        _distance_point_segment(c, a, b),
        _distance_point_segment(d, a, b),
    )


def _bounds(points: Polygon) -> tuple[float, float, float, float]:
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _polygons_conflict(first: Polygon, second: Polygon, clearance: float) -> bool:
    first_bounds, second_bounds = _bounds(first), _bounds(second)
    if (
        first_bounds[2] + clearance <= second_bounds[0] + EPSILON
        or second_bounds[2] + clearance <= first_bounds[0] + EPSILON
        or first_bounds[3] + clearance <= second_bounds[1] + EPSILON
        or second_bounds[3] + clearance <= first_bounds[1] + EPSILON
    ):
        return False
    for first_edge in _edges(first):
        for second_edge in _edges(second):
            if _segments_intersect(*first_edge, *second_edge, proper_only=True):
                return True
    if any(_point_location(point, second) == 1 for point in first):
        return True
    if any(_point_location(point, first) == 1 for point in second):
        return True
    if _bounds(first) == _bounds(second) and all(_point_location(point, second) == 0 for point in first):
        return True
    if clearance > EPSILON:
        minimum = min(
            _segment_distance(*first_edge, *second_edge)
            for first_edge in _edges(first)
            for second_edge in _edges(second)
        )
        return minimum < clearance - EPSILON
    return False


def _validate_polygon(raw_points: list[list[float]] | list[tuple[float, float]]) -> Polygon:
    if not isinstance(raw_points, list) or not 3 <= len(raw_points) <= MAX_CONTOUR_POINTS + 1:
        raise CorelBridgeError(
            f"contour_points_inches must contain 3 to {MAX_CONTOUR_POINTS} coordinate pairs.",
            ErrorCode.INVALID_ARGUMENT,
        )
    points: Polygon = []
    for index, raw in enumerate(raw_points):
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise CorelBridgeError(f"Contour point {index + 1} must be an [x, y] pair.", ErrorCode.INVALID_ARGUMENT)
        points.append((_coordinate(f"contour point {index + 1} x", raw[0]), _coordinate(f"contour point {index + 1} y", raw[1])))
    if len(points) > 3 and math.dist(points[0], points[-1]) <= EPSILON:
        points.pop()
    if len(points) < 3 or _polygon_area(points) <= EPSILON:
        raise CorelBridgeError("The cut contour must enclose a positive area.", ErrorCode.INVALID_ARGUMENT)
    edges = list(_edges(points))
    for first_index, first in enumerate(edges):
        for second_index in range(first_index + 1, len(edges)):
            if second_index in (first_index, first_index + 1) or (first_index == 0 and second_index == len(edges) - 1):
                continue
            if _segments_intersect(*first, *edges[second_index]):
                raise CorelBridgeError("The cut contour must be a simple, non-self-intersecting polygon.", ErrorCode.INVALID_ARGUMENT)
    minimum_x, minimum_y, maximum_x, maximum_y = _bounds(points)
    width, height = maximum_x - minimum_x, maximum_y - minimum_y
    if width < 0.01 or height < 0.01:
        raise CorelBridgeError("The cut contour must be at least 0.01 inch wide and high.", ErrorCode.INVALID_ARGUMENT)
    return [(point[0] - minimum_x, point[1] - minimum_y) for point in points]


def _rotate_180(points: Polygon) -> Polygon:
    _, _, maximum_x, maximum_y = _bounds(points)
    return [(maximum_x - point[0], maximum_y - point[1]) for point in points]


def _translate(points: Polygon, x: float, y: float) -> Polygon:
    return [(point[0] + x, point[1] + y) for point in points]


def _sheet_variants(width: float, height: float, policy: str) -> list[tuple[float, float, bool]]:
    supplied = (width, height, False)
    portrait = (min(width, height), max(width, height), width > height)
    landscape = (max(width, height), min(width, height), width < height)
    requested = {
        "fixed": [supplied],
        "portrait": [portrait],
        "landscape": [landscape],
        "best_fit": [supplied, portrait, landscape],
    }[policy]
    result: list[tuple[float, float, bool]] = []
    seen: set[tuple[float, float]] = set()
    for item in requested:
        if item[:2] not in seen:
            seen.add(item[:2])
            result.append(item)
    return result


def _row_polygons(polygon: Polygon, columns: int, left: float, baseline: float, horizontal_pitch: float) -> list[Polygon]:
    return [_translate(polygon, left + column * horizontal_pitch, baseline) for column in range(columns)]


def _rows_conflict(new_row: list[Polygon], existing: list[Polygon], clearance: float, footprint_width: float) -> bool:
    for new_polygon in new_row:
        new_left, _, new_right, _ = _bounds(new_polygon)
        for existing_polygon in existing:
            old_left, _, old_right, _ = _bounds(existing_polygon)
            if old_right + clearance < new_left - EPSILON or new_right + clearance < old_left - EPSILON:
                continue
            if _polygons_conflict(new_polygon, existing_polygon, clearance):
                return True
    return False


def _closest_safe_baseline(
    polygon: Polygon,
    columns: int,
    left: float,
    horizontal_pitch: float,
    previous_baseline: float,
    existing_polygons: list[Polygon],
    height: float,
    clearance: float,
    tolerance: float,
) -> float:
    high = previous_baseline + height + clearance
    step = max(tolerance * 4, min(0.02, height / 100.0))
    valid = high
    trial = high - step
    minimum = previous_baseline + tolerance
    while trial >= minimum:
        row = _row_polygons(polygon, columns, left, trial, horizontal_pitch)
        if _rows_conflict(row, existing_polygons, clearance, _bounds(polygon)[2]):
            low = trial
            while valid - low > tolerance:
                midpoint = (low + valid) / 2.0
                midpoint_row = _row_polygons(polygon, columns, left, midpoint, horizontal_pitch)
                if _rows_conflict(midpoint_row, existing_polygons, clearance, _bounds(polygon)[2]):
                    low = midpoint
                else:
                    valid = midpoint
            return valid
        valid = trial
        trial -= step
    return max(minimum, valid)


def _build_candidate(
    pattern: tuple[int, ...],
    strategy: str,
    polygons: dict[int, Polygon],
    columns: int,
    left: float,
    bottom: float,
    top_limit: float,
    horizontal_pitch: float,
    height: float,
    clearance: float,
    tolerance: float,
    sheet_width: float,
    sheet_height: float,
    orientation_changed: bool,
    contour_area: float,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    all_polygons: list[Polygon] = []
    baseline = bottom
    row_index = 0
    while row_index < MAX_CONTOUR_ROWS:
        rotation = pattern[row_index % len(pattern)]
        polygon = polygons[rotation]
        if row_index:
            baseline = _closest_safe_baseline(
                polygon, columns, left, horizontal_pitch, rows[-1]["baseline_inches"],
                all_polygons, height, clearance, tolerance,
            )
        if baseline + height > top_limit + EPSILON:
            break
        row_polygons = _row_polygons(polygon, columns, left, baseline, horizontal_pitch)
        if _rows_conflict(row_polygons, all_polygons, clearance, _bounds(polygon)[2]):
            break
        rows.append({"row": row_index + 1, "rotation_degrees": rotation, "baseline_inches": baseline})
        all_polygons.extend(row_polygons)
        row_index += 1
    if row_index == MAX_CONTOUR_ROWS and baseline + height <= top_limit:
        raise CorelBridgeError("Contour nesting exceeds the supported 2,000-row limit.", ErrorCode.INVALID_ARGUMENT)

    capacity = len(rows) * columns
    placements: list[dict[str, Any]] = []
    for row in rows:
        for column in range(columns):
            if len(placements) >= MAX_CONTOUR_PLACEMENTS:
                break
            placements.append({
                "copy": len(placements) + 1,
                "row": row["row"],
                "column": column + 1,
                "x_inches": round(left + column * horizontal_pitch, 6),
                "y_inches": round(row["baseline_inches"], 6),
                "rotation_degrees": row["rotation_degrees"],
            })
        if len(placements) >= MAX_CONTOUR_PLACEMENTS:
            break
    rectangular_pitch = height + clearance
    nested = any(
        rows[index]["baseline_inches"] - rows[index - 1]["baseline_inches"] < rectangular_pitch - tolerance
        for index in range(1, len(rows))
    )
    sheet_area = sheet_width * sheet_height
    waste = 100.0 if not capacity else max(0.0, 100.0 * (1.0 - capacity * contour_area / sheet_area))
    return {
        "layout_strategy": strategy,
        "sheet_width_inches": sheet_width,
        "sheet_height_inches": sheet_height,
        "sheet_orientation": "portrait" if sheet_height >= sheet_width else "landscape",
        "sheet_orientation_changed": orientation_changed,
        "columns": columns,
        "rows": len(rows),
        "capacity": capacity,
        "rotation_used": any(row["rotation_degrees"] for row in rows),
        "nested_rows": nested,
        "waste_percent": round(waste, 3),
        "cutting_complexity": "moderate" if nested else "simple",
        "cutting_complexity_score": 1 if nested else 0,
        "row_details": rows,
        "placements": placements,
        "placements_truncated": capacity > len(placements),
    }


def plan_contour_nesting(
    contour_points_inches: list[list[float]],
    sheet_width_inches: float,
    sheet_height_inches: float,
    quantity: int = 1,
    margin_inches: float = 0.25,
    gutter_inches: float = 0.0,
    bleed_inches: float = 0.0,
    cutting_method: str = "unknown",
    allow_180_rotation: bool | None = None,
    sheet_orientation: str = "fixed",
    geometry_tolerance_inches: float = 0.0005,
) -> dict[str, Any]:
    """Plan safe complete rows using actual cut contours and optional 180-degree pairing."""
    if cutting_method not in CUTTING_METHODS:
        raise CorelBridgeError(
            "cutting_method must be unknown, digital_cutter, die_cut, or guillotine.",
            ErrorCode.INVALID_ARGUMENT,
        )
    classification = classify_imposition_job(
        "contour", True, cutting_method, allow_180_rotation, False,
    )
    if classification["requires_clarification"]:
        return {
            "ready": False,
            "workflow": classification["workflow"],
            "questions": classification["questions"],
            "blocking_issues": classification["blocking_issues"],
        }
    if classification["workflow"] != "contour_nesting":
        raise CorelBridgeError(
            "Guillotine-only work must use rectangular N-up; contour interlocking is not permitted.",
            ErrorCode.INVALID_ARGUMENT,
        )
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_CONTOUR_QUANTITY:
        raise CorelBridgeError(f"quantity must be an integer from 1 to {MAX_CONTOUR_QUANTITY}.", ErrorCode.INVALID_ARGUMENT)
    if sheet_orientation not in SHEET_ORIENTATIONS:
        raise CorelBridgeError("sheet_orientation must be fixed, portrait, landscape, or best_fit.", ErrorCode.INVALID_ARGUMENT)
    sheet_width = _number("sheet_width_inches", sheet_width_inches, positive=True)
    sheet_height = _number("sheet_height_inches", sheet_height_inches, positive=True)
    margin = _number("margin_inches", margin_inches)
    gutter = _number("gutter_inches", gutter_inches)
    bleed = _number("bleed_inches", bleed_inches)
    tolerance = _number("geometry_tolerance_inches", geometry_tolerance_inches, positive=True)
    if max(sheet_width, sheet_height) > 200 or margin > 20 or gutter > 20 or bleed > 2 or tolerance > 0.05:
        raise CorelBridgeError("Contour nesting dimensions exceed the supported production range.", ErrorCode.INVALID_ARGUMENT)

    polygon = _validate_polygon(contour_points_inches)
    _, _, footprint_width, footprint_height = _bounds(polygon)
    required_clearance = gutter + bleed * 2
    # Preserve the requested production gap after curve flattening and COM
    # coordinate rounding. Shared-cut-line jobs with a requested zero gap stay
    # at zero so exact common boundaries remain possible.
    clearance = required_clearance + tolerance if required_clearance > 0 else 0.0
    effective_margin = margin + bleed
    contour_area = _polygon_area(polygon)
    polygons = {0: polygon, 180: _rotate_180(polygon)}
    patterns = [((0,), "upright_contour_rows")]
    if allow_180_rotation:
        patterns.extend([
            ((180,), "rotated_180_contour_rows"),
            ((0, 180), "alternating_0_180_rows"),
            ((180, 0), "alternating_180_0_rows"),
        ])

    candidates: list[dict[str, Any]] = []
    for width, height, changed in _sheet_variants(sheet_width, sheet_height, sheet_orientation):
        usable_width = width - effective_margin * 2
        usable_height = height - effective_margin * 2
        if usable_width <= 0 or usable_height <= 0:
            continue
        columns = max(0, math.floor((usable_width + clearance) / (footprint_width + clearance) + EPSILON))
        if columns > MAX_CONTOUR_COLUMNS:
            raise CorelBridgeError("Contour nesting exceeds the supported 500-column limit.", ErrorCode.INVALID_ARGUMENT)
        if columns == 0 or footprint_height > usable_height + EPSILON:
            for pattern, strategy in patterns:
                candidates.append({
                    "layout_strategy": strategy,
                    "sheet_width_inches": width,
                    "sheet_height_inches": height,
                    "sheet_orientation": "portrait" if height >= width else "landscape",
                    "sheet_orientation_changed": changed,
                    "columns": 0,
                    "rows": 0,
                    "capacity": 0,
                    "rotation_used": bool(pattern[0]),
                    "nested_rows": False,
                    "waste_percent": 100.0,
                    "cutting_complexity": "simple",
                    "cutting_complexity_score": 0,
                    "row_details": [],
                    "placements": [],
                })
            continue
        horizontal_pitch = footprint_width + clearance
        for pattern, strategy in patterns:
            candidates.append(_build_candidate(
                pattern, strategy, polygons, columns, effective_margin, effective_margin,
                height - effective_margin, horizontal_pitch, footprint_height, clearance,
                tolerance, width, height, changed, contour_area,
            ))

    if not candidates:
        raise CorelBridgeError("Margins and bleed leave no usable sheet area.", ErrorCode.INVALID_ARGUMENT)
    strategy_rank = {
        "upright_contour_rows": 0,
        "rotated_180_contour_rows": 1,
        "alternating_0_180_rows": 2,
        "alternating_180_0_rows": 3,
    }
    candidates.sort(key=lambda item: (
        -item["capacity"], item["waste_percent"], item["cutting_complexity_score"],
        item["sheet_orientation_changed"], strategy_rank[item["layout_strategy"]],
    ))
    selected = candidates[0]
    capacity = selected["capacity"]
    sheets = math.ceil(quantity / capacity) if capacity else 0
    alternatives = [{key: value for key, value in candidate.items() if key not in ("placements", "row_details")} for candidate in candidates]
    for index, alternative in enumerate(alternatives):
        alternative["selected"] = index == 0
    return {
        "ready": capacity > 0,
        "workflow": "contour_nesting",
        "layout_strategy": selected["layout_strategy"],
        "sheet_width_inches": selected["sheet_width_inches"],
        "sheet_height_inches": selected["sheet_height_inches"],
        "sheet_orientation": selected["sheet_orientation"],
        "sheet_orientation_changed": selected["sheet_orientation_changed"],
        "footprint_width_inches": round(footprint_width, 6),
        "footprint_height_inches": round(footprint_height, 6),
        "contour_area_square_inches": round(contour_area, 6),
        "columns": selected["columns"],
        "rows": selected["rows"],
        "copies_per_sheet": capacity,
        "requested_quantity": quantity,
        "sheets_required": sheets,
        "total_produced": sheets * capacity,
        "overage": sheets * capacity - quantity if capacity else 0,
        "margin_inches": margin,
        "bleed_inches": bleed,
        "gutter_inches": gutter,
        "required_contour_clearance_inches": round(required_clearance, 6),
        "effective_contour_clearance_inches": round(clearance, 6),
        "geometry_tolerance_inches": tolerance,
        "rotation_used": selected["rotation_used"],
        "nested_rows": selected["nested_rows"],
        "waste_percent": selected["waste_percent"],
        "cutting_complexity": selected["cutting_complexity"],
        "scale_percent": 100.0,
        "contour_points_inches": [[round(x, 6), round(y, 6)] for x, y in polygon],
        "row_details": selected["row_details"],
        "placements": selected["placements"],
        "alternatives": alternatives,
        "placements_truncated": selected.get("placements_truncated", False),
        "questions": [],
        "blocking_issues": [],
    }


def plan_imposition_layout(
    contour_points_inches: list[list[float]],
    footprint_kind: str,
    workflow: str,
    sheet_width_inches: float,
    sheet_height_inches: float,
    quantity: int = 1,
    margin_inches: float = 0.25,
    gutter_inches: float = 0.0,
    bleed_inches: float = 0.0,
    cutting_method: str = "unknown",
    allow_180_rotation: bool = False,
    sheet_orientation: str = "fixed",
    geometry_tolerance_inches: float = 0.0005,
) -> dict[str, Any]:
    """Build one normalized vector-imposition plan for rectangular or contour routing."""
    if footprint_kind not in {"rectangular", "contour"}:
        raise CorelBridgeError("footprint_kind must be rectangular or contour.", ErrorCode.INVALID_ARGUMENT)
    if workflow not in {"rectangular_n_up", "contour_nesting"}:
        raise CorelBridgeError("workflow must be rectangular_n_up or contour_nesting.", ErrorCode.INVALID_ARGUMENT)
    if not isinstance(allow_180_rotation, bool):
        raise CorelBridgeError("allow_180_rotation must be a boolean.", ErrorCode.INVALID_ARGUMENT)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_CONTOUR_QUANTITY:
        raise CorelBridgeError(f"quantity must be an integer from 1 to {MAX_CONTOUR_QUANTITY}.", ErrorCode.INVALID_ARGUMENT)

    if workflow == "contour_nesting":
        return plan_contour_nesting(
            contour_points_inches,
            sheet_width_inches,
            sheet_height_inches,
            quantity=quantity,
            margin_inches=margin_inches,
            gutter_inches=gutter_inches,
            bleed_inches=bleed_inches,
            cutting_method=cutting_method,
            allow_180_rotation=allow_180_rotation,
            sheet_orientation=sheet_orientation,
            geometry_tolerance_inches=geometry_tolerance_inches,
        )

    polygon = _validate_polygon(contour_points_inches)
    _, _, footprint_width, footprint_height = _bounds(polygon)
    sheet_width = _number("sheet_width_inches", sheet_width_inches, positive=True)
    sheet_height = _number("sheet_height_inches", sheet_height_inches, positive=True)
    margin = _number("margin_inches", margin_inches)
    gutter = _number("gutter_inches", gutter_inches)
    bleed = _number("bleed_inches", bleed_inches)
    tolerance = _number("geometry_tolerance_inches", geometry_tolerance_inches, positive=True)
    if max(sheet_width, sheet_height) > 200 or margin > 20 or gutter > 20 or bleed > 2 or tolerance > 0.05:
        raise CorelBridgeError("Imposition dimensions exceed the supported production range.", ErrorCode.INVALID_ARGUMENT)

    required_clearance = gutter + bleed * 2
    effective_clearance = required_clearance + tolerance if required_clearance > 0 else 0.0
    effective_margin = margin + bleed
    layout = calculate_sheet_layout(
        footprint_width,
        footprint_height,
        sheet_width,
        sheet_height,
        effective_margin,
        effective_clearance,
        False,
        "never",
        sheet_orientation,
        requested_quantity=quantity,
    )
    capacity = int(layout["copies_per_sheet"])
    result = {
        **layout,
        "ready": bool(layout["fits"]),
        "workflow": "rectangular_n_up",
        "footprint_kind": footprint_kind,
        "footprint_width_inches": round(footprint_width, 6),
        "footprint_height_inches": round(footprint_height, 6),
        "requested_quantity": quantity,
        "sheets_required": math.ceil(quantity / capacity) if capacity else 0,
        "total_produced": math.ceil(quantity / capacity) * capacity if capacity else 0,
        "overage": math.ceil(quantity / capacity) * capacity - quantity if capacity else 0,
        "margin_inches": margin,
        "bleed_inches": bleed,
        "gutter_inches": gutter,
        "required_contour_clearance_inches": round(required_clearance, 6),
        "effective_contour_clearance_inches": round(effective_clearance, 6),
        "geometry_tolerance_inches": tolerance,
        "contour_points_inches": [[round(x, 6), round(y, 6)] for x, y in polygon],
        "questions": [],
        "blocking_issues": [],
    }
    return result


def imposition_plan_fingerprint(payload: dict[str, Any]) -> str:
    """Return a deterministic approval token for a fully materialized plan payload."""
    try:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CorelBridgeError("The imposition plan cannot be fingerprinted safely.", ErrorCode.INTERNAL_ERROR) from exc
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def contours_have_conflicts(contours: list[list[list[float]]], clearance_inches: float) -> bool:
    """Verify already transformed contours using the same deterministic collision rules."""
    clearance = _number("clearance_inches", clearance_inches)
    polygons: list[Polygon] = []
    for contour_index, contour in enumerate(contours):
        if not isinstance(contour, list) or len(contour) < 3:
            raise CorelBridgeError("Each verification contour must contain at least three points.", ErrorCode.INVALID_ARGUMENT)
        polygons.append([
            (
                _coordinate(f"contour {contour_index + 1} x", point[0]),
                _coordinate(f"contour {contour_index + 1} y", point[1]),
            )
            for point in contour
        ])
    return any(
        _polygons_conflict(first, second, clearance)
        for index, first in enumerate(polygons)
        for second in polygons[index + 1:]
    )
