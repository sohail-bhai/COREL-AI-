"""Recreate the supplied Alhamdulillah reference as an editable A4 vector CDR.

The photograph is used only as a visual reference.  The CorelDRAW document is
built from native rectangles, ellipses, Bezier curves, fountain fills, groups,
and editable artistic text.  No bitmap is imported or embedded in the CDR.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pythoncom


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corel_operator.corel_bridge import CorelBridge


MM_PER_INCH = 25.4
PAGE_WIDTH = 297.0 / MM_PER_INCH
PAGE_HEIGHT = 210.0 / MM_PER_INCH
ART_MARGIN = 0.22
ART_LEFT = ART_MARGIN
ART_BOTTOM = ART_MARGIN
ART_RIGHT = PAGE_WIDTH - ART_MARGIN
ART_TOP = PAGE_HEIGHT - ART_MARGIN


def _rgb(app: Any, value: str) -> Any:
    value = value.lstrip("#")
    return app.CreateRGBColor(
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )


def _rgb_tuple(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )


def _mix_color(start: str, end: str, amount: float) -> str:
    """Return a deterministic RGB interpolation as a Corel-compatible hex value."""
    amount = max(0.0, min(1.0, float(amount)))
    first = _rgb_tuple(start)
    second = _rgb_tuple(end)
    channels = [round(a + (b - a) * amount) for a, b in zip(first, second)]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def _sample_color_ramp(stops: list[tuple[float, str]], amount: float) -> str:
    amount = max(0.0, min(1.0, float(amount)))
    for (left_pos, left_color), (right_pos, right_color) in zip(stops, stops[1:]):
        if amount <= right_pos:
            span = max(right_pos - left_pos, 1e-9)
            return _mix_color(left_color, right_color, (amount - left_pos) / span)
    return stops[-1][1]


def _uniform(shape: Any, app: Any, color: str) -> None:
    shape.Fill.ApplyUniformFill(_rgb(app, color))


def _no_outline(shape: Any) -> None:
    shape.Outline.SetNoOutline()


def _outline(shape: Any, app: Any, color: str, width_inches: float) -> None:
    shape.Outline.Color = _rgb(app, color)
    shape.Outline.Width = float(width_inches)


def _fountain(
    shape: Any,
    app: Any,
    stops: list[tuple[int, str]],
    angle: float = 0.0,
) -> None:
    """Apply a native CorelDRAW linear fountain fill with ordered stops."""
    fountain = shape.Fill.ApplyFountainFill(
        _rgb(app, stops[0][1]),
        _rgb(app, stops[-1][1]),
        1,
        float(angle),
        256,
        0,
        50,
        0,
    )
    for position, color in stops[1:-1]:
        fountain.Colors.Add(_rgb(app, color), int(position))


def _curve_shape(
    app: Any,
    document: Any,
    layer: Any,
    name: str,
    commands: Iterable[tuple[Any, ...]],
) -> Any:
    curve = app.CreateCurve(document)
    subpath = None
    for command in commands:
        operation = command[0]
        if operation == "M":
            subpath = curve.CreateSubPath(float(command[1]), float(command[2]))
        elif operation == "L" and subpath is not None:
            subpath.AppendLineSegment(float(command[1]), float(command[2]))
        elif operation == "C" and subpath is not None:
            subpath.AppendCurveSegment2(
                float(command[5]),
                float(command[6]),
                float(command[1]),
                float(command[2]),
                float(command[3]),
                float(command[4]),
            )
        elif operation == "Z" and subpath is not None:
            subpath.Closed = True
        else:
            raise ValueError(f"Invalid pen command: {command!r}")
    shape = layer.CreateCurve(curve)
    shape.Name = name
    return shape


def _group(app: Any, shapes: list[Any], name: str) -> Any | None:
    if not shapes:
        return None
    try:
        shape_range = app.CreateShapeRange()
        for shape in shapes:
            shape_range.Add(shape)
        grouped = shape_range.Group()
        grouped.Name = name
        return grouped
    except Exception as exc:
        raise RuntimeError(f"CorelDRAW could not group {name!r}: {exc}") from exc


def _quatrefoil(
    app: Any,
    document: Any,
    layer: Any,
    cx: float,
    cy: float,
    hx: float,
    hy: float,
    name: str,
) -> Any:
    """Create one symmetrical, rounded Moroccan-trellis cell."""
    return _curve_shape(app, document, layer, name, [
        ("M", cx, cy + hy),
        ("C", cx + 0.29 * hx, cy + hy, cx + 0.50 * hx, cy + 0.80 * hy, cx + 0.50 * hx, cy + 0.55 * hy),
        ("C", cx + 0.78 * hx, cy + 0.55 * hy, cx + hx, cy + 0.32 * hy, cx + hx, cy),
        ("C", cx + hx, cy - 0.32 * hy, cx + 0.78 * hx, cy - 0.55 * hy, cx + 0.50 * hx, cy - 0.55 * hy),
        ("C", cx + 0.50 * hx, cy - 0.80 * hy, cx + 0.29 * hx, cy - hy, cx, cy - hy),
        ("C", cx - 0.29 * hx, cy - hy, cx - 0.50 * hx, cy - 0.80 * hy, cx - 0.50 * hx, cy - 0.55 * hy),
        ("C", cx - 0.78 * hx, cy - 0.55 * hy, cx - hx, cy - 0.32 * hy, cx - hx, cy),
        ("C", cx - hx, cy + 0.32 * hy, cx - 0.78 * hx, cy + 0.55 * hy, cx - 0.50 * hx, cy + 0.55 * hy),
        ("C", cx - 0.50 * hx, cy + 0.80 * hy, cx - 0.29 * hx, cy + hy, cx, cy + hy),
        ("Z",),
    ])


def _draw_background(app: Any, document: Any, layer: Any) -> list[Any]:
    page_white = layer.CreateRectangle2(0.0, 0.0, PAGE_WIDTH, PAGE_HEIGHT)
    page_white.Name = "Page_White_Margin"
    _uniform(page_white, app, "#FFFFFF")
    _no_outline(page_white)

    field = layer.CreateRectangle2(
        ART_LEFT,
        ART_BOTTOM,
        ART_RIGHT - ART_LEFT,
        ART_TOP - ART_BOTTOM,
    )
    field.Name = "Warm_Parchment_Field"
    _fountain(field, app, [
        (0, "#F4E6B8"),
        (38, "#E5C997"),
        (72, "#D19A78"),
        (100, "#BF8068"),
    ], angle=90.0)
    _no_outline(field)
    return [page_white, field]


def _draw_pattern(app: Any, document: Any, layer: Any) -> Any | None:
    shapes: list[Any] = []
    hx = 0.275
    hy = 0.315
    dx = 0.55
    dy = 0.54
    row = 0
    cy = ART_BOTTOM - hy
    while cy <= ART_TOP + hy + 1e-6:
        offset = 0.5 * dx if row % 2 else 0.0
        cx = ART_LEFT - hx + offset
        column = 0
        while cx <= ART_RIGHT + hx + 1e-6:
            motif = _quatrefoil(
                app,
                document,
                layer,
                cx,
                cy,
                hx,
                hy,
                f"Trellis_{row + 1:02d}_{column + 1:02d}",
            )
            motif.Fill.ApplyNoFill()
            _outline(motif, app, "#4B454B", 0.0115)
            shapes.append(motif)
            column += 1
            cx += dx
        row += 1
        cy += dy
    pattern = _group(app, shapes, "Moroccan_Quatrefoil_Trellis")

    # The source has a crisp white print margin.  These native white rectangles
    # act as a vector clipping frame so edge cells can continue naturally to,
    # and be cut cleanly at, the art boundary without entering the margin.
    masks = [
        (0.0, 0.0, PAGE_WIDTH, ART_BOTTOM, "Pattern_Clip_Bottom"),
        (0.0, ART_TOP, PAGE_WIDTH, PAGE_HEIGHT - ART_TOP, "Pattern_Clip_Top"),
        (0.0, ART_BOTTOM, ART_LEFT, ART_TOP - ART_BOTTOM, "Pattern_Clip_Left"),
        (ART_RIGHT, ART_BOTTOM, PAGE_WIDTH - ART_RIGHT, ART_TOP - ART_BOTTOM, "Pattern_Clip_Right"),
    ]
    for left, bottom, width, height, name in masks:
        mask = layer.CreateRectangle2(left, bottom, width, height)
        mask.Name = name
        _uniform(mask, app, "#FFFFFF")
        _no_outline(mask)
    return pattern


def _draw_plaque(app: Any, document: Any, layer: Any) -> Any:
    left = ART_LEFT
    right = ART_RIGHT
    bottom = 0.86
    shape = _curve_shape(app, document, layer, "Scalloped_Dark_Plaque", [
        ("M", left, bottom),
        ("L", right, bottom),
        ("L", right, 5.73),
        ("L", 10.66, 5.73),
        ("C", 10.38, 5.73, 10.23, 5.93, 10.19, 6.20),
        ("C", 10.13, 6.55, 9.88, 6.83, 9.54, 6.92),
        ("C", 9.25, 7.00, 9.12, 7.17, 9.10, 7.45),
        ("C", 9.07, 7.76, 8.81, ART_TOP, 8.49, ART_TOP),
        ("L", 3.20, ART_TOP),
        ("C", 2.88, ART_TOP, 2.62, 7.76, 2.59, 7.45),
        ("C", 2.57, 7.17, 2.44, 7.00, 2.15, 6.92),
        ("C", 1.81, 6.83, 1.56, 6.55, 1.50, 6.20),
        ("C", 1.46, 5.93, 1.31, 5.73, 1.03, 5.73),
        ("L", left, 5.73),
        ("L", left, bottom),
        ("Z",),
    ])
    _fountain(shape, app, [
        (0, "#101719"),
        (38, "#1B2021"),
        (67, "#2C2526"),
        (100, "#422A29"),
    ], angle=90.0)
    _no_outline(shape)
    return shape


def _ellipse(layer: Any, cx: float, cy: float, radius: float, name: str) -> Any:
    shape = layer.CreateEllipse2(cx, cy, radius, radius)
    shape.Name = name
    return shape


def _draw_glow(
    app: Any,
    document: Any,
    layer: Any,
    cx: float,
    cy: float,
    radius: float,
    name: str,
) -> Any | None:
    plaque_ramp = [
        (0.0, "#101719"),
        (0.38, "#1B2021"),
        (0.67, "#2C2526"),
        (1.0, "#422A29"),
    ]
    local_background = _sample_color_ramp(plaque_ramp, cy / PAGE_HEIGHT)
    light_ramp = [
        (0.0, local_background),
        (0.30, "#593027"),
        (0.54, "#9C4D2A"),
        (0.75, "#DF7838"),
        (0.90, "#F7B564"),
        (0.98, "#FFE0A1"),
        (1.0, "#FFF9DB"),
    ]
    shapes: list[Any] = []
    ring_count = 22
    for index in range(ring_count):
        progress = index / (ring_count - 1)
        ratio = 1.0 - 0.955 * progress
        color = _sample_color_ramp(light_ramp, progress ** 1.45)
        circle = _ellipse(layer, cx, cy, radius * ratio, f"{name}_Halo_{index:02d}")
        _uniform(circle, app, color)
        _no_outline(circle)
        shapes.append(circle)
    return _group(app, shapes, name)


def _ray(
    app: Any,
    document: Any,
    layer: Any,
    cx: float,
    cy: float,
    half_length: float,
    thickness: float,
    angle: float,
    color: str,
    name: str,
) -> Any:
    shape = _curve_shape(app, document, layer, name, [
        ("M", cx - half_length, cy),
        ("L", cx, cy + thickness / 2.0),
        ("L", cx + half_length, cy),
        ("L", cx, cy - thickness / 2.0),
        ("Z",),
    ])
    _uniform(shape, app, color)
    _no_outline(shape)
    if angle:
        shape.Rotate(float(angle))
    return shape


def _draw_starburst(
    app: Any,
    document: Any,
    layer: Any,
    cx: float,
    cy: float,
    size: float,
    name: str,
) -> Any | None:
    shapes: list[Any] = []
    glow = _draw_glow(app, document, layer, cx, cy, size * 0.27, f"{name}_Core_Glow")
    if glow is not None:
        shapes.append(glow)
    for index, angle in enumerate((0.0, 45.0, 90.0, 135.0), 1):
        diagonal = angle in (45.0, 135.0)
        multiplier = 0.66 if diagonal else 1.0
        shapes.append(_ray(
            app, document, layer, cx, cy, size * multiplier, 0.052,
            angle, "#9D4D28", f"{name}_Outer_Ray_{index}",
        ))
        shapes.append(_ray(
            app, document, layer, cx, cy, size * 0.76 * multiplier, 0.021,
            angle, "#F2A34F", f"{name}_Gold_Ray_{index}",
        ))
        shapes.append(_ray(
            app, document, layer, cx, cy, size * 0.42 * multiplier, 0.007,
            angle, "#FFF1BE", f"{name}_Light_Ray_{index}",
        ))
    core = _ellipse(layer, cx, cy, 0.025, f"{name}_White_Core")
    _uniform(core, app, "#FFFBE8")
    _no_outline(core)
    shapes.append(core)
    return _group(app, shapes, name)


def _draw_lights(app: Any, document: Any, layer: Any) -> None:
    glow_specs = [
        (0.80, 1.80, 0.085, "Glow_Left_Lower_01"),
        (0.91, 2.66, 0.125, "Glow_Left_Lower_02"),
        (0.55, 3.66, 0.075, "Glow_Left_Middle_01"),
        (1.43, 2.42, 0.075, "Glow_Left_Lower_03"),
        (1.25, 3.84, 0.080, "Glow_Left_Middle_02"),
        (1.16, 5.31, 0.205, "Glow_Left_Upper_Main"),
        (2.12, 3.44, 0.175, "Glow_Left_Centre_Main"),
        (2.98, 6.01, 0.080, "Glow_Upper_01"),
        (4.83, 6.27, 0.070, "Glow_Upper_02"),
        (8.43, 7.04, 0.075, "Glow_Upper_Right"),
        (10.31, 3.69, 0.190, "Glow_Right_Main"),
    ]
    for cx, cy, radius, name in glow_specs:
        _draw_glow(app, document, layer, cx, cy, radius, name)

    _draw_starburst(app, document, layer, 9.69, 4.62, 0.94, "Main_Eight_Point_Flare")
    _draw_starburst(app, document, layer, 5.68, 7.72, 0.24, "Upper_Centre_Sparkle")


def _create_artistic_text(
    layer: Any,
    text: str,
    font: str,
    size_points: float,
    bold: bool,
) -> Any:
    try:
        return layer.CreateArtisticText(
            0.0, 0.0, text, 0, -1, font, float(size_points), -1 if bold else 0, 0,
        )
    except Exception:
        return layer.CreateArtisticText(
            0.0, 0.0, text, 0, 1, font, float(size_points), -1 if bold else 0, 0,
        )


def _fit_text(
    shape: Any,
    name: str,
    left: float,
    bottom: float,
    box_width: float,
    box_height: float,
) -> dict[str, float]:
    width = float(shape.SizeWidth)
    height = float(shape.SizeHeight)
    scale = min(box_width / width, box_height / height)
    final_width = width * scale
    final_height = height * scale
    shape.SetSize(final_width, final_height)
    actual_left = left + (box_width - final_width) / 2.0
    actual_bottom = bottom + (box_height - final_height) / 2.0
    shape.SetPosition(actual_left, actual_bottom)
    shape.Name = name
    return {
        "left": actual_left,
        "bottom": actual_bottom,
        "width": final_width,
        "height": final_height,
    }


def _place_text_exact(
    shape: Any,
    name: str,
    left: float,
    bottom: float,
    width: float,
    height: float,
) -> dict[str, float]:
    """Fit calligraphy to measured reference bounds, including horizontal scale."""
    shape.SetSize(width, height)
    shape.SetPosition(left, bottom)
    shape.Name = name
    return {
        "left": left,
        "bottom": bottom,
        "width": width,
        "height": height,
    }


def _draw_swash(app: Any, document: Any, layer: Any) -> None:
    lower = _curve_shape(app, document, layer, "Calligraphy_Lower_Sweep", [
        ("M", 2.70, 3.35),
        ("C", 4.01, 2.79, 7.00, 2.80, 9.30, 3.78),
        ("C", 7.61, 3.12, 5.02, 3.17, 3.02, 3.63),
        ("C", 2.86, 3.61, 2.73, 3.51, 2.70, 3.35),
        ("Z",),
    ])
    _fountain(lower, app, [
        (0, "#A85A35"),
        (38, "#F0D88B"),
        (66, "#D8963F"),
        (100, "#F8E6A4"),
    ], angle=4.0)
    _no_outline(lower)

    rise = _curve_shape(app, document, layer, "Calligraphy_Left_Rising_Sweep", [
        ("M", 2.92, 3.48),
        ("C", 2.55, 3.87, 2.39, 4.47, 2.55, 5.04),
        ("C", 2.62, 4.55, 2.83, 4.09, 3.18, 3.66),
        ("C", 3.12, 3.53, 3.02, 3.46, 2.92, 3.48),
        ("Z",),
    ])
    _fountain(rise, app, [
        (0, "#C27438"),
        (55, "#F4D98D"),
        (100, "#B45F36"),
    ], angle=78.0)
    _no_outline(rise)


def _draw_typography(app: Any, document: Any, layer: Any) -> dict[str, Any]:
    _draw_swash(app, document, layer)

    arabic = "ٱلْحَمْدُ لِلَّٰهِ"
    arabic_box = (2.70, 3.07, 6.30, 3.72)
    arabic_shadow = _create_artistic_text(layer, arabic, "Aldhabi", 240.0, False)
    _place_text_exact(
        arabic_shadow,
        "Arabic_Calligraphy_Shadow_Editable",
        arabic_box[0] + 0.045,
        arabic_box[1] - 0.045,
        arabic_box[2],
        arabic_box[3],
    )
    _uniform(arabic_shadow, app, "#703A28")
    _no_outline(arabic_shadow)

    arabic_gold = _create_artistic_text(layer, arabic, "Aldhabi", 240.0, False)
    arabic_bounds = _place_text_exact(
        arabic_gold,
        "Arabic_Alhamdulillah_Editable",
        *arabic_box,
    )
    _fountain(arabic_gold, app, [
        (0, "#A95B35"),
        (25, "#E0A954"),
        (48, "#F7E7A8"),
        (72, "#D6963F"),
        (100, "#F2D78B"),
    ], angle=4.0)
    _no_outline(arabic_gold)

    english = "Alhamdulillah"
    english_box = (1.62, 1.42, 9.10, 1.02)
    english_shadow = _create_artistic_text(layer, english, "Bookman Old Style", 72.0, True)
    _place_text_exact(
        english_shadow,
        "English_Alhamdulillah_Shadow_Editable",
        english_box[0] + 0.035,
        english_box[1] - 0.035,
        english_box[2],
        english_box[3],
    )
    _uniform(english_shadow, app, "#6A3623")
    _no_outline(english_shadow)

    english_gold = _create_artistic_text(layer, english, "Bookman Old Style", 72.0, True)
    english_bounds = _place_text_exact(
        english_gold,
        "English_Alhamdulillah_Editable",
        *english_box,
    )
    _fountain(english_gold, app, [
        (0, "#B86E39"),
        (28, "#F0D18A"),
        (52, "#FFF0B7"),
        (76, "#D89A43"),
        (100, "#E8C36F"),
    ], angle=1.0)
    _no_outline(english_gold)

    return {
        "arabic_text": arabic,
        "arabic_font": "Aldhabi",
        "arabic_bounds_inches": arabic_bounds,
        "english_text": english,
        "english_font": "Bookman Old Style Bold",
        "english_bounds_inches": english_bounds,
    }


def _walk_shapes(shapes: Any) -> Iterable[Any]:
    for index in range(1, int(shapes.Count) + 1):
        shape = shapes.Item(index)
        yield shape
        if int(shape.Type) == 7:
            yield from _walk_shapes(shape.Shapes)


def _vector_audit(document: Any) -> dict[str, Any]:
    counts = Counter()
    names: list[str] = []
    editable_text: list[dict[str, str]] = []
    for shape in _walk_shapes(document.ActivePage.Shapes):
        shape_type = int(shape.Type)
        counts[shape_type] += 1
        name = str(getattr(shape, "Name", "") or "")
        if name:
            names.append(name)
        if shape_type == 6:
            try:
                editable_text.append({
                    "name": name,
                    "content": str(shape.Text.Story.Text),
                })
            except Exception:
                editable_text.append({"name": name, "content": "<readback unavailable>"})
    return {
        "shape_type_counts": {
            "curve": counts[3],
            "bitmap": counts[5],
            "editable_text": counts[6],
            "group": counts[7],
            "other_vector_primitives": sum(
                value for key, value in counts.items() if key not in (3, 5, 6, 7)
            ),
        },
        "contains_no_bitmap_shapes": counts[5] == 0,
        "editable_text_objects": editable_text,
        "named_object_count": len(names),
    }


def _configure_pdf(document: Any) -> dict[str, Any]:
    settings = document.PDFSettings
    settings.Reset()
    requested = {
        "PublishRange": 1,
        "pdfVersion": 4,
        "ColorMode": 1,
        "UseColorProfile": True,
        "TextAsCurves": True,
        "EmbedFonts": False,
        "ComplexFillsAsBitmaps": False,
        "FountainSteps": 256,
        "DownsampleColor": False,
        "DownsampleGray": False,
        "DownsampleMono": False,
        "IncludeBleed": False,
        "CropMarks": False,
        "RegistrationMarks": False,
        "Author": "CorelDRAW AI Operator Prototype",
        "Subject": "A4 Alhamdulillah editable vector recreation",
    }
    applied: dict[str, Any] = {}
    unavailable: dict[str, str] = {}
    for property_name, value in requested.items():
        try:
            setattr(settings, property_name, value)
            applied[property_name] = getattr(settings, property_name)
        except Exception as exc:
            unavailable[property_name] = f"{type(exc).__name__}: {exc}"
    return {"applied": applied, "unavailable_optional_properties": unavailable}


def _pdf_audit(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    media = re.search(
        rb"/MediaBox\s*\[\s*([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)",
        data,
    )
    media_inches = None
    if media:
        x1, y1, x2, y2 = (float(value) for value in media.groups())
        media_inches = {
            "width": round((x2 - x1) / 72.0, 4),
            "height": round((y2 - y1) / 72.0, 4),
        }
    return {
        "bytes": len(data),
        "media_box_inches": media_inches,
        "embedded_image_objects": data.count(b"/Subtype /Image"),
    }


def _render_preview(pdf_path: Path, preview_path: Path) -> None:
    import pymupdf

    pdf = pymupdf.open(pdf_path)
    try:
        page = pdf[0]
        zoom = 1500.0 / float(page.rect.width)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        pixmap.save(preview_path)
    finally:
        pdf.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    output_dir = args.output_dir or ROOT / "output" / f"alhamdulillah_a4_vector_{datetime.now():%Y%m%d_%H%M%S}"
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    cdr_path = output_dir / "Alhamdulillah_A4_Landscape_Editable_Vector.cdr"
    pdf_path = output_dir / "Alhamdulillah_A4_Landscape_Vector.pdf"
    preview_path = output_dir / "verification_preview_not_in_artwork.png"
    audit_path = output_dir / "vector_recreation_audit.json"

    pythoncom.CoInitialize()
    bridge = CorelBridge()
    try:
        bridge.connect()
        bridge.create_document(PAGE_WIDTH, PAGE_HEIGHT)
        document = bridge.target_doc
        app = bridge.app
        if document is None or app is None:
            raise RuntimeError("CorelDRAW did not expose the new A4 document.")
        app.Visible = True
        page = document.ActivePage

        background_layer = page.ActiveLayer
        background_layer.Name = "01 - Background"
        pattern_layer = page.CreateLayer("02 - Moroccan Pattern")
        plaque_layer = page.CreateLayer("03 - Dark Plaque")
        lights_layer = page.CreateLayer("04 - Vector Light Accents")
        typography_layer = page.CreateLayer("05 - Editable Typography")

        with bridge._in_inches(document), bridge._reference_point(document, bridge.CDR_BOTTOM_LEFT):
            _draw_background(app, document, background_layer)
            _draw_pattern(app, document, pattern_layer)
            _draw_plaque(app, document, plaque_layer)
            _draw_lights(app, document, lights_layer)
            typography = _draw_typography(app, document, typography_layer)

        vector_audit = _vector_audit(document)
        if not vector_audit["contains_no_bitmap_shapes"]:
            raise RuntimeError(f"Bitmap audit failed: {vector_audit}")

        pdf_settings = _configure_pdf(document)
        bridge.save_document(str(cdr_path))
        document.PublishToPDF(str(pdf_path))
        if not pdf_path.is_file():
            raise RuntimeError("CorelDRAW returned without creating the vector PDF.")

        pdf_audit = _pdf_audit(pdf_path)
        if pdf_audit["embedded_image_objects"] != 0:
            raise RuntimeError(f"The PDF unexpectedly contains raster image objects: {pdf_audit}")
        _render_preview(pdf_path, preview_path)

        try:
            app.ActiveWindow.ActiveView.ToFitPage()
        except Exception:
            pass

        audit = {
            "result": "PASS_EDITABLE_VECTOR_RECREATION",
            "source_method": "Native CorelDRAW vector primitives, hand-authored Bezier paths, gradients, and editable text; no bitmap imported",
            "page": {
                "standard": "A4 landscape",
                "width_mm": 297.0,
                "height_mm": 210.0,
                "width_inches": PAGE_WIDTH,
                "height_inches": PAGE_HEIGHT,
            },
            "typography": typography,
            "vector_audit": vector_audit,
            "pdf_settings": pdf_settings,
            "pdf_audit": pdf_audit,
            "artifacts": {
                "editable_cdr": str(cdr_path),
                "vector_pdf": str(pdf_path),
                "verification_preview_not_used_in_artwork": str(preview_path),
            },
            "approximation_notes": [
                "The supplied source is a perspective photograph, so physical placement was normalized to exact A4 landscape geometry.",
                "Aldhabi and Bookman Old Style were selected as the closest installed fonts; both remain editable in the CDR.",
                "Glow effects are concentric vector ellipses and vector rays rather than raster effects.",
            ],
        }
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "result": audit["result"],
            "output_dir": str(output_dir),
            "editable_cdr": str(cdr_path),
            "vector_pdf": str(pdf_path),
            "preview": str(preview_path),
            "bitmap_shapes": vector_audit["shape_type_counts"]["bitmap"],
            "editable_text_objects": vector_audit["shape_type_counts"]["editable_text"],
            "pdf_embedded_images": pdf_audit["embedded_image_objects"],
        }, indent=2, ensure_ascii=False))
        return 0
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
