"""Pure geometry plans and bounded validation for common layout edits."""
from __future__ import annotations

import math
from .errors import CorelBridgeError, ErrorCode
from .adapters import CorelX7Adapter
from .typography import finite_number

FLIP_AXES = CorelX7Adapter.FLIP_AXES
ORDER_METHODS = {"front": "OrderToFront", "back": "OrderToBack",
                 "forward_one": "OrderForwardOne", "back_one": "OrderBackOne"}
MAX_LAYOUT_OBJECTS = 100
POSITION_TOLERANCE = 0.001


def choice(value, field, values):
    if type(value) is not str or value not in values:
        raise CorelBridgeError(f"{field} must be one of: {', '.join(values)}.", ErrorCode.INVALID_ARGUMENT)


def validate_rotation(angle, relative, center_x, center_y):
    finite_number(angle, "angle_degrees", -36000, 36000)
    if type(relative) is not bool:
        raise CorelBridgeError("relative must be a boolean.", ErrorCode.INVALID_ARGUMENT)
    if (center_x is None) != (center_y is None):
        raise CorelBridgeError("Supply both rotation center coordinates or neither.", ErrorCode.INVALID_ARGUMENT)
    if center_x is not None:
        finite_number(center_x, "center_x_inches", -10000, 10000)
        finite_number(center_y, "center_y_inches", -10000, 10000)


def matrix_determinant(matrix):
    return matrix[0]*matrix[3] - matrix[1]*matrix[2]


def circular_difference(left, right):
    return abs((left-right+180) % 360 - 180)


def plan_distribution(bounds, axis, mode="equal_gaps", spacing_inches=None, allow_overlap=False):
    choice(axis, "axis", ("horizontal", "vertical"))
    choice(mode, "mode", ("equal_gaps", "equal_centers"))
    if type(allow_overlap) is not bool:
        raise CorelBridgeError("allow_overlap must be a boolean.", ErrorCode.INVALID_ARGUMENT)
    if spacing_inches is not None:
        finite_number(spacing_inches, "spacing_inches", -200, 200)
        if mode != "equal_gaps":
            raise CorelBridgeError("Explicit spacing_inches requires equal_gaps mode.", ErrorCode.INVALID_ARGUMENT)
    if not 3 <= len(bounds) <= MAX_LAYOUT_OBJECTS:
        raise CorelBridgeError("Distribution requires 3-100 independent objects.", ErrorCode.INVALID_ARGUMENT)
    position, size = ("x", "width") if axis=="horizontal" else ("y", "height")
    ordered = sorted(range(len(bounds)), key=lambda i: bounds[i][position] + (bounds[i][size]/2 if mode=="equal_centers" else 0))
    first, last = bounds[ordered[0]], bounds[ordered[-1]]
    targets = []
    if mode == "equal_gaps":
        # Preserve the outer extent, including a wider middle object that already
        # protrudes beyond the last object's edge.
        outer_end = max(b[position]+b[size] for b in bounds)
        gap = spacing_inches if spacing_inches is not None else (outer_end-first[position]-sum(b[size] for b in bounds))/(len(bounds)-1)
        cursor = first[position]
        for index in ordered:
            target = dict(bounds[index])
            target[position] = cursor
            targets.append({"input_index": index, "bounds": target})
            cursor += bounds[index][size] + gap
    else:
        start = first[position]+first[size]/2
        end = last[position]+last[size]/2
        gap = (end-start)/(len(bounds)-1)
        for rank, index in enumerate(ordered):
            target = dict(bounds[index])
            target[position] = start+rank*gap-bounds[index][size]/2
            targets.append({"input_index": index, "bounds": target})
    if any(not math.isfinite(v) for target in targets for v in target["bounds"].values()):
        raise CorelBridgeError("The planned distribution has unrepresentable coordinates.", ErrorCode.INVALID_ARGUMENT)
    overlaps = any(a["bounds"][position]+a["bounds"][size] > b["bounds"][position]+POSITION_TOLERANCE
                   for a,b in zip(targets,targets[1:]))
    if overlaps and not allow_overlap:
        raise CorelBridgeError("The requested distribution overlaps objects; increase the extent/spacing or explicitly allow_overlap.", ErrorCode.INVALID_ARGUMENT)
    return {"axis": axis, "mode": mode, "spacing_inches": gap,
            "overlap_allowed": allow_overlap, "has_overlap": overlaps, "targets": targets}
