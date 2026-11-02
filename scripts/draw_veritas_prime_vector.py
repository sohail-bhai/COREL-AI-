"""Recreate the supplied VeritasPrime reference as print-oriented vector curves.

The production document contains only CorelDRAW curve/group shapes.  The
wordmark is created from local fonts and immediately converted to curves;
no source bitmap is imported or embedded.
"""
from __future__ import annotations

import argparse
import json
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


PAGE_INCHES = 4.0
REFERENCE_PIXELS = 910.0
REFERENCE_X_OFFSET = 3.0  # Centers the supplied 904 px image in a 910 px square.


def _x(pixel: float) -> float:
    return (pixel + REFERENCE_X_OFFSET) * PAGE_INCHES / REFERENCE_PIXELS


def _y(pixel: float) -> float:
    return (REFERENCE_PIXELS - pixel) * PAGE_INCHES / REFERENCE_PIXELS


def _curve_shape(app: Any, document: Any, layer: Any, name: str, commands: Iterable[tuple[Any, ...]]) -> Any:
    """Create one closed or open pen path from line and cubic commands."""
    curve = app.CreateCurve(document)
    subpath = None
    for command in commands:
        operation = command[0]
        if operation == "M":
            subpath = curve.CreateSubPath(_x(command[1]), _y(command[2]))
        elif operation == "L" and subpath is not None:
            subpath.AppendLineSegment(_x(command[1]), _y(command[2]))
        elif operation == "C" and subpath is not None:
            subpath.AppendCurveSegment2(
                _x(command[5]),
                _y(command[6]),
                _x(command[1]),
                _y(command[2]),
                _x(command[3]),
                _y(command[4]),
            )
        elif operation == "Z" and subpath is not None:
            subpath.Closed = True
        else:
            raise ValueError(f"Invalid pen command: {command!r}")
    shape = layer.CreateCurve(curve)
    shape.Name = name
    return shape


def _circle_pen_path(app: Any, document: Any, layer: Any) -> Any:
    """Draw the circular keyline as four cubic Bezier segments."""
    cx, cy, radius = 452.0, 450.0, 390.0
    handle = radius * 0.552284749831
    return _curve_shape(app, document, layer, "Outer_Keyline_Pen_Curve", [
        ("M", cx + radius, cy),
        ("C", cx + radius, cy - handle, cx + handle, cy - radius, cx, cy - radius),
        ("C", cx - handle, cy - radius, cx - radius, cy - handle, cx - radius, cy),
        ("C", cx - radius, cy + handle, cx - handle, cy + radius, cx, cy + radius),
        ("C", cx + handle, cy + radius, cx + radius, cy + handle, cx + radius, cy),
        ("Z",),
    ])


def _symbol_pen_path(app: Any, document: Any, layer: Any) -> Any:
    """Draw the gradient V/P symbol as one hand-authored closed Bezier path."""
    return _curve_shape(app, document, layer, "VP_Symbol_Pen_Curve", [
        ("M", 290.0, 267.0),
        ("L", 346.0, 267.0),
        ("C", 355.0, 267.0, 361.0, 272.0, 366.0, 280.0),
        ("L", 415.0, 356.0),
        ("C", 421.0, 365.0, 428.0, 368.0, 437.0, 368.0),
        ("C", 446.0, 368.0, 452.0, 365.0, 458.0, 355.0),
        ("L", 502.0, 281.0),
        ("C", 507.0, 272.0, 514.0, 267.0, 524.0, 267.0),
        ("L", 564.0, 267.0),
        ("C", 590.0, 267.0, 610.0, 289.0, 610.0, 317.0),
        ("C", 610.0, 344.0, 584.0, 367.0, 554.0, 367.0),
        ("L", 479.0, 367.0),
        ("L", 425.0, 434.0),
        ("C", 417.0, 447.0, 398.0, 448.0, 389.0, 434.0),
        ("L", 290.0, 267.0),
        ("Z",),
    ])


def _cmyk(app: Any, cyan: int, magenta: int, yellow: int, black: int) -> Any:
    return app.CreateCMYKColor(cyan, magenta, yellow, black)


def _style_artwork(app: Any, keyline: Any, symbol: Any) -> None:
    keyline.Fill.ApplyNoFill()
    keyline.Outline.Color = _cmyk(app, 0, 0, 0, 100)
    keyline.Outline.Width = 0.0066  # Approximately 0.48 pt on a 4 inch page.

    symbol.Outline.SetNoOutline()
    turquoise = _cmyk(app, 68, 0, 23, 0)
    sky = _cmyk(app, 48, 8, 5, 0)
    lavender = _cmyk(app, 12, 25, 0, 0)
    fountain = symbol.Fill.ApplyFountainFill(turquoise, lavender, 1, 0.0, 256, 0, 50, 0)
    fountain.Colors.Add(sky, 52)


def _create_wordmark(app: Any, document: Any, layer: Any) -> tuple[Any, Any]:
    """Create the two-weight wordmark and permanently convert both parts to curves."""
    dark_plum = _cmyk(app, 0, 24, 3, 96)
    bold = layer.CreateArtisticText(0.0, 0.0, "Veritas", 0, -1, "Century Gothic", 30.0, -1, 0)
    regular = layer.CreateArtisticText(0.0, 0.0, "Prime", 0, -1, "Century Gothic", 30.0, 0, 0)
    for shape in (bold, regular):
        shape.Fill.ApplyUniformFill(dark_plum)
        shape.Outline.SetNoOutline()
        shape.ConvertToCurves()

    # Match the supplied reference bounds while preserving the relative font widths.
    raw_widths = [float(bold.SizeWidth), float(regular.SizeWidth)]
    raw_heights = [float(bold.SizeHeight), float(regular.SizeHeight)]
    raw_total_width = sum(raw_widths)
    target_left = _x(171.0)
    target_bottom = _y(635.0)
    target_width = _x(733.0) - target_left
    target_height = _y(563.0) - target_bottom
    x_scale = target_width / raw_total_width
    y_scale = target_height / max(raw_heights)

    cursor = target_left
    for shape, raw_width, raw_height in zip((bold, regular), raw_widths, raw_heights):
        width = raw_width * x_scale
        height = raw_height * y_scale
        shape.SetSize(width, height)
        shape.SetPosition(cursor, target_bottom + (target_height - height) / 2.0)
        cursor += width

    bold.Name = "Veritas_Bold_Converted_Curves"
    regular.Name = "Prime_Regular_Converted_Curves"
    return bold, regular


def _walk_shapes(shapes: Any) -> Iterable[Any]:
    for index in range(1, int(shapes.Count) + 1):
        shape = shapes.Item(index)
        yield shape
        if int(shape.Type) == 7:  # cdrGroupShape
            yield from _walk_shapes(shape.Shapes)


def _vector_audit(document: Any) -> dict[str, Any]:
    counts = Counter()
    names: list[str] = []
    for shape in _walk_shapes(document.ActivePage.Shapes):
        shape_type = int(shape.Type)
        counts[shape_type] += 1
        name = str(getattr(shape, "Name", "") or "")
        if name:
            names.append(name)
    return {
        "shape_type_counts": {
            "curve": counts[3],
            "bitmap": counts[5],
            "text": counts[6],
            "group": counts[7],
            "other": sum(value for key, value in counts.items() if key not in (3, 5, 6, 7)),
        },
        "all_production_objects_are_vector": counts[5] == 0 and counts[6] == 0,
        "object_names": names,
    }


def _configure_print_pdf(document: Any) -> dict[str, Any]:
    settings = document.PDFSettings
    settings.Reset()
    requested = {
        "PublishRange": 1,  # pdfCurrentPage
        "pdfVersion": 4,  # PDF/X-1a in CorelDRAW X7
        "ColorMode": 1,  # pdfCMYK
        "ColorProfile": 0,  # composite output profile
        "UseColorProfile": True,
        "TextAsCurves": True,
        "EmbedFonts": False,
        "ComplexFillsAsBitmaps": False,
        "FountainSteps": 256,
        "DownsampleColor": False,
        "DownsampleGray": False,
        "DownsampleMono": False,
        "ConvertSpotColors": True,
        "OutputSpotColorsAs": 2,  # pdfSpotAsCMYK
        "IncludeBleed": False,
        "CropMarks": False,
        "RegistrationMarks": False,
        "Author": "CorelDRAW AI Operator Prototype",
        "Subject": "VeritasPrime pen-curve vector recreation test",
    }
    applied: dict[str, Any] = {}
    unavailable: dict[str, str] = {}
    for property_name, value in requested.items():
        try:
            setattr(settings, property_name, value)
            applied[property_name] = getattr(settings, property_name)
        except Exception as exc:
            unavailable[property_name] = f"{type(exc).__name__}: {exc}"

    critical = {
        "PublishRange": 1,
        "pdfVersion": 4,
        "ColorMode": 1,
        "TextAsCurves": True,
        "ComplexFillsAsBitmaps": False,
    }
    mismatches = {
        name: {"expected": expected, "actual": applied.get(name)}
        for name, expected in critical.items()
        if applied.get(name) != expected
    }
    if mismatches:
        raise RuntimeError(f"CorelDRAW X7 rejected critical PDF/X settings: {mismatches}; unavailable={unavailable}")
    return {
        "standard": "PDF/X-1a",
        "color_mode": "CMYK",
        "text_as_curves": True,
        "complex_fills_as_bitmaps": False,
        "fountain_steps": 256,
        "bleed_inches": 0.0,
        "reason_no_bleed": "The supplied white artwork does not print to the finished edge.",
        "applied_properties": applied,
        "unavailable_optional_properties": unavailable,
    }


def _pdf_audit(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    media = re.search(rb"/MediaBox\s*\[\s*([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)", data)
    media_inches = None
    if media:
        x1, y1, x2, y2 = (float(value) for value in media.groups())
        media_inches = {"width": round((x2 - x1) / 72.0, 4), "height": round((y2 - y1) / 72.0, 4)}
    return {
        "bytes": len(data),
        "media_box_inches": media_inches,
        "embedded_image_objects": data.count(b"/Subtype /Image"),
        "font_file_tokens": data.count(b"/FontFile"),
        "output_intent_tokens": data.count(b"/OutputIntent"),
        "device_cmyk_tokens": data.count(b"/DeviceCMYK"),
    }


def _render_preview(pdf_path: Path, preview_path: Path) -> None:
    import pymupdf

    pdf = pymupdf.open(pdf_path)
    try:
        page = pdf[0]
        zoom = 910.0 / 288.0
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        pixmap.save(preview_path)
    finally:
        pdf.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    output_dir = args.output_dir or ROOT / "output" / f"veritas_prime_vector_test_{datetime.now():%Y%m%d_%H%M%S}"
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    cdr_path = output_dir / "veritas_prime_pen_curves.cdr"
    pdf_path = output_dir / "veritas_prime_print_PDFX1a.pdf"
    preview_path = output_dir / "verification_preview.png"
    audit_path = output_dir / "production_audit.json"

    pythoncom.CoInitialize()
    bridge = CorelBridge()
    try:
        bridge.connect()
        bridge.create_document(PAGE_INCHES, PAGE_INCHES)
        document = bridge.target_doc
        app = bridge.app
        if document is None or app is None:
            raise RuntimeError("CorelDRAW did not expose the newly created document.")
        layer = document.ActivePage.ActiveLayer
        layer.Name = "Pen Curves - Print Artwork"

        with bridge._in_inches(document), bridge._reference_point(document, bridge.CDR_BOTTOM_LEFT):
            keyline = _circle_pen_path(app, document, layer)
            symbol = _symbol_pen_path(app, document, layer)
            _style_artwork(app, keyline, symbol)
            _create_wordmark(app, document, layer)

        vector_audit = _vector_audit(document)
        if not vector_audit["all_production_objects_are_vector"]:
            raise RuntimeError(f"Vector-only audit failed: {vector_audit}")

        print_settings = _configure_print_pdf(document)
        bridge.save_document(str(cdr_path))
        document.PublishToPDF(str(pdf_path))
        if not pdf_path.is_file():
            raise RuntimeError("CorelDRAW returned without creating the production PDF.")

        pdf_audit = _pdf_audit(pdf_path)
        if pdf_audit["embedded_image_objects"] != 0:
            raise RuntimeError(f"The production PDF unexpectedly contains raster image objects: {pdf_audit}")
        _render_preview(pdf_path, preview_path)

        audit = {
            "result": "PASS_VECTOR_PRINT_TEST",
            "source_method": "Hand-authored line and cubic Bezier paths; wordmark converted to curves",
            "page": {"finished_width_inches": PAGE_INCHES, "finished_height_inches": PAGE_INCHES},
            "vector_audit": vector_audit,
            "print_settings": print_settings,
            "pdf_audit": pdf_audit,
            "artifacts": {
                "editable_cdr": str(cdr_path),
                "production_pdf": str(pdf_path),
                "raster_verification_preview_not_used_in_artwork": str(preview_path),
            },
        }
        audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
        print(json.dumps(audit, indent=2))
        return 0
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
