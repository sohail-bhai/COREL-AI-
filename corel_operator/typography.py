"""Bounded text validation and native readback; no COM connections or writes."""
from __future__ import annotations

import math
from typing import Any

from .errors import CorelBridgeError, ErrorCode

MAX_FONT_CHARS = 200
MAX_FONT_SCAN = 10000
MAX_TEXT_CHARS = 100000
ALIGNMENTS = {"left": 1, "right": 2, "center": 3, "justify": 4, "force_justify": 5}
UNDERLINES = {"none": 0, "single": 1}
TEXT_TYPES = {0: "artistic", 1: "paragraph", 2: "artistic_fitted", 3: "paragraph_fitted"}
STYLE_ATTRIBUTES = {"font": "Font", "size_points": "Size", "bold": "Bold",
                    "italic": "Italic", "underline": "Underline", "alignment": "Alignment"}


def invalid(message: str):
    raise CorelBridgeError(message, ErrorCode.INVALID_ARGUMENT)


def finite_number(value: Any, field: str, minimum: float, maximum: float) -> float:
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum
    except (OverflowError, TypeError, ValueError):
        valid = False
    if not valid:
        invalid(f"{field} must be a finite number between {minimum:g} and {maximum:g}.")
    return float(value)


def validate_font(font: Any) -> None:
    if (type(font) is not str or not font.strip() or font != font.strip()
            or len(font) > MAX_FONT_CHARS or any(ord(c) < 32 for c in font)):
        invalid("font must be a nonblank name of at most 200 characters without outer whitespace or controls.")


def validate_style(font=None, size_points=None, bold=None, italic=None, underline=None, alignment=None):
    values = dict(font=font, size_points=size_points, bold=bold, italic=italic,
                  underline=underline, alignment=alignment)
    if font is not None:
        validate_font(font)
    if size_points is not None:
        finite_number(size_points, "size_points", 1, 500)
    for field in ("bold", "italic"):
        if values[field] is not None and type(values[field]) is not bool:
            invalid(f"{field} must be a boolean or null.")
    for field, allowed in (("underline", UNDERLINES), ("alignment", ALIGNMENTS)):
        if values[field] is not None and (type(values[field]) is not str or values[field] not in allowed):
            invalid(f"{field} must be one of: {', '.join(allowed)}.")
    requested = {field: value for field, value in values.items() if value is not None}
    if not requested:
        invalid("Supply at least one text style property.")
    return requested


def validate_paragraph(text, x, y, width, height, object_name):
    if type(text) is not str or not text.strip() or len(text) > MAX_TEXT_CHARS or "\x00" in text:
        invalid("text must contain 1-100000 characters, with visible content and no NUL.")
    finite_number(x, "x_inches", -10000, 10000)
    finite_number(y, "y_inches", -10000, 10000)
    finite_number(width, "width_inches", 0.001, 200)
    finite_number(height, "height_inches", 0.001, 200)
    if type(object_name) is not str or len(object_name) > 120 or any(ord(c) < 32 for c in object_name):
        invalid("object_name must be at most 120 characters without controls.")


def read_property(value, attr, kind):
    try:
        result = getattr(value, attr)
        if kind == "number":
            return float(result) if type(result) in (int, float) and math.isfinite(result) else None
        if kind == "integer":
            return result if type(result) is int else None
        if kind == "boolean":
            if type(result) is bool:
                return result
            return {0: False, -1: True}.get(result) if type(result) is int else None
        if kind == "font":
            return result if type(result) is str and 0 < len(result) <= MAX_FONT_CHARS else None
    except Exception:
        return None


def style_readback(story):
    result = {}
    for field, attr in STYLE_ATTRIBUTES.items():
        kind = "font" if field == "font" else "number" if field == "size_points" else "boolean" if field in ("bold", "italic") else "integer"
        value = read_property(story, attr, kind)
        if field == "size_points" and value is not None and value <= 0:
            value = None
        if field in ("underline", "alignment"):
            value = {v: k for k, v in (UNDERLINES if field == "underline" else ALIGNMENTS).items()}.get(value)
        result[field] = value
    result["unavailable_or_mixed_properties"] = [key for key, value in result.items() if value is None]
    return result


def layout_readback(text, story):
    """Overflow is native linked-story overflow, never a geometric or glyph-fit guess."""
    code = read_property(text, "Type", "integer")
    result = {"text_type_code": code, "text_type": TEXT_TYPES.get(code),
              "overflow": None, "overflow_scope": "linked_story",
              "frame_count": None,
              "char_spacing_native": read_property(story, "CharSpacing", "number"),
              "word_spacing_native": read_property(story, "WordSpacing", "number"),
              "line_spacing_native": read_property(story, "LineSpacing", "number"),
              "line_spacing_type_code": read_property(story, "LineSpacingType", "integer")}
    if code in (1, 3):
        result["overflow"] = read_property(text, "Overflow", "boolean")
    try:
        count = read_property(text.Frames, "Count", "integer")
        result["frame_count"] = count if count is not None and 0 <= count <= 10000 else None
    except Exception:
        pass
    result["unavailable_properties"] = [key for key, value in result.items()
                                        if value is None and (key != "overflow" or code in (1, 3))]
    return result
