"""Pure, deterministic design-plan schema, validation, and preview engine."""
from __future__ import annotations

import math
from typing import Any

from jsonschema import Draft202012Validator

from .errors import CorelBridgeError, ErrorCode

PLAN_SCHEMA_VERSION = "1.0"
MAX_PLAN_ELEMENTS = 200

DESIGN_PLAN_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CorelDesignPlanV1",
    "type": "object",
    "required": ["version", "name", "canvas", "elements"],
    "additionalProperties": False,
    "properties": {
        "version": {
            "type": "string",
            "const": "1.0",
        },
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
        },
        "description": {
            "type": "string",
            "maxLength": 500,
        },
        "canvas": {
            "type": "object",
            "required": ["width_inches", "height_inches"],
            "additionalProperties": False,
            "properties": {
                "width_inches": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 200,
                },
                "height_inches": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 200,
                },
                "unit": {
                    "type": "string",
                    "enum": ["inch"],
                    "default": "inch",
                },
            },
        },
        "elements": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_PLAN_ELEMENTS,
            "items": {
                "type": "object",
                "required": ["id", "type"],
                "additionalProperties": False,
                "properties": {
                    "id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 64,
                    },
                    "type": {
                        "type": "string",
                        "enum": ["rectangle", "ellipse", "text", "artwork"],
                    },
                    "x_inches": {
                        "type": "number",
                        "minimum": -200,
                        "maximum": 400,
                    },
                    "y_inches": {
                        "type": "number",
                        "minimum": -200,
                        "maximum": 400,
                    },
                    "width_inches": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "maximum": 200,
                    },
                    "height_inches": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "maximum": 200,
                    },
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 5000,
                    },
                    "font": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100,
                        "default": "Arial",
                    },
                    "font_size_points": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "maximum": 500,
                        "default": 24.0,
                    },
                    "bold": {
                        "type": "boolean",
                        "default": False,
                    },
                    "file_path": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 2048,
                    },
                    "fill": {
                        "type": "object",
                        "required": ["red", "green", "blue"],
                        "additionalProperties": False,
                        "properties": {
                            "red": {"type": "integer", "minimum": 0, "maximum": 255},
                            "green": {"type": "integer", "minimum": 0, "maximum": 255},
                            "blue": {"type": "integer", "minimum": 0, "maximum": 255},
                        },
                    },
                    "outline": {
                        "type": "object",
                        "required": ["width_points"],
                        "additionalProperties": False,
                        "properties": {
                            "width_points": {"type": "number", "minimum": 0, "maximum": 72},
                            "red": {"type": "integer", "minimum": 0, "maximum": 255, "default": 0},
                            "green": {"type": "integer", "minimum": 0, "maximum": 255, "default": 0},
                            "blue": {"type": "integer", "minimum": 0, "maximum": 255, "default": 0},
                        },
                    },
                },
                "allOf": [
                    {
                        "if": {
                            "properties": {"type": {"enum": ["rectangle", "ellipse"]}},
                            "required": ["type"],
                        },
                        "then": {
                            "required": ["x_inches", "y_inches", "width_inches", "height_inches"],
                        },
                    },
                    {
                        "if": {
                            "properties": {"type": {"const": "text"}},
                            "required": ["type"],
                        },
                        "then": {
                            "required": ["x_inches", "y_inches", "text"],
                        },
                    },
                    {
                        "if": {
                            "properties": {"type": {"const": "artwork"}},
                            "required": ["type"],
                        },
                        "then": {
                            "required": ["file_path"],
                        },
                    },
                ],
            },
        },
        "validations": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "expected_element_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_PLAN_ELEMENTS,
                },
                "bounding_box_within_canvas": {"type": "boolean", "default": True},
            },
        },
    },
}


_DESIGN_PLAN_VALIDATOR = Draft202012Validator(DESIGN_PLAN_SCHEMA)


def _format_schema_path(parts: Any) -> str:
    path = "plan"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _validate_design_plan_schema(plan: dict[str, Any]) -> None:
    errors = sorted(
        _DESIGN_PLAN_VALIDATOR.iter_errors(plan),
        key=lambda error: (
            _format_schema_path(error.absolute_path),
            ".".join(str(part) for part in error.absolute_schema_path),
        ),
    )
    if not errors:
        return

    error = errors[0]
    path = _format_schema_path(error.absolute_path)
    raise CorelBridgeError(
        f"Design plan schema validation failed at {path}: {error.message}",
        ErrorCode.INVALID_ARGUMENT,
        {
            "path": path,
            "validator": str(error.validator),
        },
    )


def validate_design_plan(plan: Any) -> dict[str, Any]:
    """Pure, deterministic validation of a design plan against the schema and domain rules."""
    if not isinstance(plan, dict):
        raise CorelBridgeError("Design plan must be a JSON object.", ErrorCode.INVALID_ARGUMENT)

    _validate_design_plan_schema(plan)

    if plan.get("version") != PLAN_SCHEMA_VERSION:
        raise CorelBridgeError(
            f"Unsupported plan version {plan.get('version')!r}; expected {PLAN_SCHEMA_VERSION!r}.",
            ErrorCode.INVALID_ARGUMENT,
        )

    name = plan.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CorelBridgeError("Plan 'name' must be a non-empty string.", ErrorCode.INVALID_ARGUMENT)

    canvas = plan.get("canvas")
    if not isinstance(canvas, dict):
        raise CorelBridgeError("Plan 'canvas' must be an object with width_inches and height_inches.", ErrorCode.INVALID_ARGUMENT)

    cw = canvas.get("width_inches")
    ch = canvas.get("height_inches")
    for dim_name, val in (("width_inches", cw), ("height_inches", ch)):
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val <= 0 or val > 200:
            raise CorelBridgeError(f"canvas.{dim_name} must be a positive finite number <= 200 inches.", ErrorCode.INVALID_ARGUMENT)

    elements = plan.get("elements")
    if not isinstance(elements, list) or not elements:
        raise CorelBridgeError("Plan 'elements' must be a non-empty array of objects.", ErrorCode.INVALID_ARGUMENT)
    if len(elements) > MAX_PLAN_ELEMENTS:
        raise CorelBridgeError(f"Plan contains {len(elements)} elements; maximum allowed is {MAX_PLAN_ELEMENTS}.", ErrorCode.INVALID_ARGUMENT)

    seen_ids: set[str] = set()
    elements_by_type: dict[str, int] = {}
    warnings: list[str] = []
    blocking_issues: list[str] = []
    validations = plan.get("validations", {})
    require_bounds_within_canvas = validations.get("bounding_box_within_canvas", True)

    for index, elem in enumerate(elements, start=1):
        if not isinstance(elem, dict):
            raise CorelBridgeError(f"Element at index {index} must be an object.", ErrorCode.INVALID_ARGUMENT)

        elem_id = elem.get("id")
        if not isinstance(elem_id, str) or not elem_id.strip():
            raise CorelBridgeError(f"Element at index {index} is missing a non-empty string 'id'.", ErrorCode.INVALID_ARGUMENT)
        if elem_id in seen_ids:
            raise CorelBridgeError(f"Duplicate element id {elem_id!r} in design plan.", ErrorCode.INVALID_ARGUMENT)
        seen_ids.add(elem_id)

        elem_type = elem.get("type")
        if elem_type not in ("rectangle", "ellipse", "text", "artwork"):
            raise CorelBridgeError(
                f"Element {elem_id!r} has unsupported type {elem_type!r}; "
                "expected 'rectangle', 'ellipse', 'text', or 'artwork'.",
                ErrorCode.INVALID_ARGUMENT,
            )
        elements_by_type[elem_type] = elements_by_type.get(elem_type, 0) + 1

        x = elem.get("x_inches")
        y = elem.get("y_inches")
        if x is not None:
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
                raise CorelBridgeError(f"Element {elem_id!r}: x_inches must be a finite number.", ErrorCode.INVALID_ARGUMENT)
        if y is not None:
            if isinstance(y, bool) or not isinstance(y, (int, float)) or not math.isfinite(y):
                raise CorelBridgeError(f"Element {elem_id!r}: y_inches must be a finite number.", ErrorCode.INVALID_ARGUMENT)

        w = elem.get("width_inches")
        h = elem.get("height_inches")
        for dim_name, val in (("width_inches", w), ("height_inches", h)):
            if val is not None and (
                isinstance(val, bool)
                or not isinstance(val, (int, float))
                or not math.isfinite(val)
                or val <= 0
                or val > 200
            ):
                raise CorelBridgeError(
                    f"Element {elem_id!r}: {dim_name} must be a positive finite number <= 200.",
                    ErrorCode.INVALID_ARGUMENT,
                )
        if elem_type in ("rectangle", "ellipse"):
            if x is None or y is None:
                raise CorelBridgeError(f"Element {elem_id!r}: x_inches and y_inches are required for {elem_type}.", ErrorCode.INVALID_ARGUMENT)

        if elem_type == "text":
            text_val = elem.get("text")
            if not isinstance(text_val, str) or not text_val.strip():
                raise CorelBridgeError(f"Element {elem_id!r}: text element must have non-empty 'text'.", ErrorCode.INVALID_ARGUMENT)
            if x is None or y is None:
                raise CorelBridgeError(f"Element {elem_id!r}: x_inches and y_inches are required for text.", ErrorCode.INVALID_ARGUMENT)
            size_pt = elem.get("font_size_points", 24.0)
            if isinstance(size_pt, bool) or not isinstance(size_pt, (int, float)) or not (1 <= size_pt <= 500):
                raise CorelBridgeError(f"Element {elem_id!r}: font_size_points must be between 1 and 500.", ErrorCode.INVALID_ARGUMENT)
            font = elem.get("font", "Arial")
            if not isinstance(font, str) or not font.strip():
                raise CorelBridgeError(
                    f"Element {elem_id!r}: font must be a non-empty string.",
                    ErrorCode.INVALID_ARGUMENT,
                )

        if elem_type == "artwork":
            file_path = elem.get("file_path")
            if not isinstance(file_path, str) or not file_path.strip():
                raise CorelBridgeError(f"Element {elem_id!r}: artwork must have a non-empty 'file_path'.", ErrorCode.INVALID_ARGUMENT)

        fill = elem.get("fill")
        if fill is not None:
            if not isinstance(fill, dict):
                raise CorelBridgeError(f"Element {elem_id!r}: 'fill' must be an object with red, green, blue integers.", ErrorCode.INVALID_ARGUMENT)
            for c_name in ("red", "green", "blue"):
                c_val = fill.get(c_name)
                if isinstance(c_val, bool) or not isinstance(c_val, int) or not (0 <= c_val <= 255):
                    raise CorelBridgeError(f"Element {elem_id!r}: fill.{c_name} must be integer 0-255.", ErrorCode.INVALID_ARGUMENT)

        outline = elem.get("outline")
        if outline is not None:
            if not isinstance(outline, dict):
                raise CorelBridgeError(f"Element {elem_id!r}: 'outline' must be an object.", ErrorCode.INVALID_ARGUMENT)
            ow = outline.get("width_points")
            if isinstance(ow, bool) or not isinstance(ow, (int, float)) or not (0 <= ow <= 72):
                raise CorelBridgeError(f"Element {elem_id!r}: outline.width_points must be between 0 and 72.", ErrorCode.INVALID_ARGUMENT)
            for c_name in ("red", "green", "blue"):
                if c_name in outline:
                    c_val = outline[c_name]
                    if isinstance(c_val, bool) or not isinstance(c_val, int) or not (0 <= c_val <= 255):
                        raise CorelBridgeError(f"Element {elem_id!r}: outline.{c_name} must be integer 0-255.", ErrorCode.INVALID_ARGUMENT)

        boundary_issues: list[str] = []
        if x is not None and y is not None:
            if x < 0 or x > cw or y < 0 or y > ch:
                boundary_issues.append(f"Element {elem_id!r} placement ({x}, {y}) is outside canvas bounds ({cw} x {ch}).")
            if w is not None and (x + w > cw):
                boundary_issues.append(f"Element {elem_id!r} right edge ({round(x + w, 2)}) exceeds canvas width ({cw}).")
            if h is not None and (y + h > ch):
                boundary_issues.append(f"Element {elem_id!r} top edge ({round(y + h, 2)}) exceeds canvas height ({ch}).")

        if require_bounds_within_canvas:
            blocking_issues.extend(boundary_issues)
        else:
            warnings.extend(boundary_issues)

    expected_count = validations.get("expected_element_count")
    if expected_count is not None and expected_count != len(elements):
        raise CorelBridgeError(
            f"Plan element count ({len(elements)}) does not match expected_element_count ({expected_count}).",
            ErrorCode.INVALID_ARGUMENT,
        )

    return {
        "valid": True,
        "name": name,
        "version": PLAN_SCHEMA_VERSION,
        "element_count": len(elements),
        "canvas": {"width_inches": cw, "height_inches": ch, "unit": "inch"},
        "elements_by_type": elements_by_type,
        "warnings": warnings,
        "blocking_issues": blocking_issues,
        "ready_for_execution": not blocking_issues,
    }


def preview_design_plan(plan: Any) -> dict[str, Any]:
    """Compute layout statistics, palette, typography, and bounding box preview without CorelDRAW."""
    validation = validate_design_plan(plan)

    canvas_w = float(plan["canvas"]["width_inches"])
    canvas_h = float(plan["canvas"]["height_inches"])
    elements = plan["elements"]

    unique_colors: list[list[int]] = []
    seen_colors: set[tuple[int, int, int]] = set()

    def add_color(rgb_dict: dict[str, Any] | None) -> None:
        if rgb_dict:
            triple = (int(rgb_dict["red"]), int(rgb_dict["green"]), int(rgb_dict["blue"]))
            if triple not in seen_colors:
                seen_colors.add(triple)
                unique_colors.append(list(triple))

    typography_list: list[dict[str, Any]] = []
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")
    total_shape_area = 0.0

    for elem in elements:
        add_color(elem.get("fill"))
        add_color(elem.get("outline"))

        x = elem.get("x_inches")
        y = elem.get("y_inches")
        w = elem.get("width_inches", 0.0)
        h = elem.get("height_inches", 0.0)

        if elem["type"] == "text":
            font_info = {
                "font": elem.get("font", "Arial"),
                "size_points": elem.get("font_size_points", 24.0),
                "bold": elem.get("bold", False),
            }
            if font_info not in typography_list:
                typography_list.append(font_info)
            # Estimate text bounding box if width/height not provided
            if w <= 0:
                char_count = len(elem.get("text", ""))
                pt = float(font_info["size_points"])
                w = round(char_count * (pt / 72.0) * 0.6, 3)
                h = round(pt / 72.0 * 1.2, 3)

        if x is not None and y is not None:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
            total_shape_area += w * h

    bounds_valid = math.isfinite(min_x) and math.isfinite(min_y)
    bounding_box = {
        "min_x_inches": round(min_x, 4) if bounds_valid else 0.0,
        "min_y_inches": round(min_y, 4) if bounds_valid else 0.0,
        "max_x_inches": round(max_x, 4) if bounds_valid else 0.0,
        "max_y_inches": round(max_y, 4) if bounds_valid else 0.0,
        "width_inches": round(max(0.0, max_x - min_x), 4) if bounds_valid else 0.0,
        "height_inches": round(max(0.0, max_y - min_y), 4) if bounds_valid else 0.0,
    }

    canvas_area = canvas_w * canvas_h
    coverage_ratio = round(min(1.0, total_shape_area / canvas_area), 4) if canvas_area > 0 else 0.0

    return {
        "valid": True,
        "name": plan["name"],
        "description": plan.get("description", ""),
        "canvas": {
            "width_inches": canvas_w,
            "height_inches": canvas_h,
            "aspect_ratio": round(canvas_w / canvas_h, 4) if canvas_h > 0 else 1.0,
            "area_sq_inches": round(canvas_area, 2),
        },
        "elements_summary": {
            "total_count": len(elements),
            "by_type": validation["elements_by_type"],
            "z_order": [elem["id"] for elem in elements],
        },
        "bounding_box": bounding_box,
        "color_palette": {
            "count": len(unique_colors),
            "colors_rgb": unique_colors,
        },
        "typography": typography_list,
        "estimated_coverage_ratio": coverage_ratio,
        "warnings": validation["warnings"],
        "blocking_issues": validation["blocking_issues"],
        "ready_for_execution": validation["ready_for_execution"],
    }
