"""Build the measured Phase 2 structure for Alhamdulillah vector V2.

The calibrated photograph is imported only on a hidden, locked, nonprinting
reference layer. Printable content in this stage is native CorelDRAW vector
geometry: page/background rectangles, a clipped trellis, and a traced plaque.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pythoncom


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corel_operator.corel_bridge import CorelBridge  # noqa: E402


MM_PER_INCH = 25.4
PAGE_WIDTH_MM = 297.0
PAGE_HEIGHT_MM = 210.0
PAGE_WIDTH = PAGE_WIDTH_MM / MM_PER_INCH
PAGE_HEIGHT = PAGE_HEIGHT_MM / MM_PER_INCH
TRELLIS_HALF_CELL_PX = 27.0
TRELLIS_PITCH_X_PX = 54.25
TRELLIS_PITCH_Y_PX = 54.75
TRELLIS_ORIGIN_X_PX = 23.0
TRELLIS_ORIGIN_Y_PX = 16.0
# Least-squares affine correction from six independently matched exposed regions.
TRELLIS_AFFINE_X = (4.509538, 0.992746289, -0.015427215)
TRELLIS_AFFINE_Y = (4.320934, -0.005060729, 0.980617089)
EXPECTED_LAYERS = (
    "00 - Reference - NONPRINTING",
    "01 - Background and Margin",
    "02 - Trellis PowerClip",
    "03 - Traced Plaque",
    "04 - Arabic Calligraphy Curves",
    "05 - English Typography",
    "06 - Vector Light Effects",
)


def _rgb(app: Any, value: str) -> Any:
    value = value.lstrip("#")
    return app.CreateRGBColor(
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )


def _uniform(shape: Any, app: Any, color: str) -> None:
    shape.Fill.ApplyUniformFill(_rgb(app, color))


def _no_fill(shape: Any) -> None:
    shape.Fill.ApplyNoFill()


def _no_outline(shape: Any) -> None:
    shape.Outline.SetNoOutline()


def _outline(shape: Any, app: Any, color: str, width_inches: float) -> None:
    shape.Outline.Color = _rgb(app, color)
    shape.Outline.Width = float(width_inches)


def _fountain(
    shape: Any,
    app: Any,
    stops: list[tuple[int, str]],
    *,
    angle: float = 0.0,
) -> None:
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


def _group(app: Any, shapes: list[Any], name: str) -> Any:
    if not shapes:
        raise ValueError(f"Cannot create empty group {name!r}.")
    shape_range = app.CreateShapeRange()
    for shape in shapes:
        shape_range.Add(shape)
    grouped = shape_range.Group()
    grouped.Name = name
    return grouped


def _load_workspace(workspace: Path) -> tuple[dict[str, Any], Path]:
    workspace = workspace.expanduser().resolve()
    manifest_path = workspace / "V2_WORKSPACE_MANIFEST.json"
    measurements_path = workspace / "v2_measurements.json"
    if not manifest_path.is_file() or not measurements_path.is_file():
        raise ValueError("Workspace must contain V2_WORKSPACE_MANIFEST.json and v2_measurements.json.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    measurements = json.loads(measurements_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PHASE_1_RECTIFIED_AND_CALIBRATED":
        raise ValueError("Workspace has not passed Phase 1 calibration.")
    reference = Path(manifest["artifacts"]["rectified_reference"]).resolve()
    if not reference.is_file():
        raise ValueError(f"Rectified reference is missing: {reference}")
    if measurements.get("schema_version") != "reference-calibration-v1":
        raise ValueError("Unsupported measurement schema.")
    return measurements, reference


def _coordinate_mapper(measurements: dict[str, Any]):
    image = measurements["rectified_image"]
    width = float(image["width_pixels"])
    height = float(image["height_pixels"])

    def point(x_pixels: float, y_pixels: float) -> tuple[float, float]:
        return (x_pixels / width * PAGE_WIDTH, (height - y_pixels) / height * PAGE_HEIGHT)

    return point


def _mapped_commands(
    point,
    commands: Iterable[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    mapped: list[tuple[Any, ...]] = []
    for command in commands:
        operation = command[0]
        if operation in {"M", "L"}:
            x, y = point(float(command[1]), float(command[2]))
            mapped.append((operation, x, y))
        elif operation == "C":
            c1 = point(float(command[1]), float(command[2]))
            c2 = point(float(command[3]), float(command[4]))
            end = point(float(command[5]), float(command[6]))
            mapped.append(("C", c1[0], c1[1], c2[0], c2[1], end[0], end[1]))
        else:
            mapped.append(command)
    return mapped


def _trellis_coordinate_mapper(point):
    def trellis_point(x: float, y: float) -> tuple[float, float]:
        mapped_x = (
            TRELLIS_AFFINE_X[0]
            + TRELLIS_AFFINE_X[1] * x
            + TRELLIS_AFFINE_X[2] * y
        )
        mapped_y = (
            TRELLIS_AFFINE_Y[0]
            + TRELLIS_AFFINE_Y[1] * x
            + TRELLIS_AFFINE_Y[2] * y
        )
        return point(mapped_x, mapped_y)

    return trellis_point


def _motif_commands(cx: float, cy: float) -> list[tuple[Any, ...]]:
    """Measured near-square quatrefoil repeat from the clear upper-left field."""
    half = TRELLIS_HALF_CELL_PX
    notch = half * 0.43
    shoulder = half * 0.72
    tangent = half * 0.30
    return [
        ("M", cx, cy - half),
        ("C", cx - tangent, cy - half, cx - notch, cy - shoulder, cx - notch, cy - notch),
        ("C", cx - shoulder, cy - notch, cx - half, cy - tangent, cx - half, cy),
        ("C", cx - half, cy + tangent, cx - shoulder, cy + notch, cx - notch, cy + notch),
        ("C", cx - notch, cy + shoulder, cx - tangent, cy + half, cx, cy + half),
        ("C", cx + tangent, cy + half, cx + notch, cy + shoulder, cx + notch, cy + notch),
        ("C", cx + shoulder, cy + notch, cx + half, cy + tangent, cx + half, cy),
        ("C", cx + half, cy - tangent, cx + shoulder, cy - notch, cx + notch, cy - notch),
        ("C", cx + notch, cy - shoulder, cx + tangent, cy - half, cx, cy - half),
        ("Z",),
    ]


def _plaque_commands(field: dict[str, float]) -> list[tuple[Any, ...]]:
    left = field["left_pixels"]
    right = field["right_pixels"]
    return [
        ("M", left, 832.0),
        ("L", left, 280.0),
        ("L", 176.0, 280.0),
        ("C", 190.0, 270.0, 194.0, 246.0, 196.0, 218.0),
        ("C", 199.0, 178.0, 220.0, 151.0, 261.0, 141.0),
        ("C", 299.0, 132.0, 311.0, 107.0, 315.0, 84.0),
        ("C", 320.0, 56.0, 350.0, 41.0, 400.0, 40.0),
        ("L", 887.0, 40.0),
        ("C", 934.0, 42.0, 963.0, 57.0, 969.0, 84.0),
        ("C", 975.0, 112.0, 991.0, 132.0, 1024.0, 140.0),
        ("C", 1071.0, 150.0, 1093.0, 176.0, 1097.0, 211.0),
        ("C", 1100.0, 246.0, 1107.0, 270.0, 1121.0, 280.0),
        ("L", right, 280.0),
        ("L", right, 832.0),
        ("Z",),
    ]


def _field_pixels(measurements: dict[str, Any]) -> dict[str, float]:
    bounds = measurements["inner_printed_field"]["average_bounds_mm"]
    image = measurements["rectified_image"]
    width = float(image["width_pixels"])
    height = float(image["height_pixels"])
    return {
        "left_pixels": float(bounds["left"]) / PAGE_WIDTH_MM * width,
        "right_pixels": float(bounds["right"]) / PAGE_WIDTH_MM * width,
        "top_pixels": (PAGE_HEIGHT_MM - float(bounds["top"])) / PAGE_HEIGHT_MM * height,
        "bottom_pixels": (PAGE_HEIGHT_MM - float(bounds["bottom"])) / PAGE_HEIGHT_MM * height,
    }


def _import_reference(
    app: Any,
    document: Any,
    layer: Any,
    reference_path: Path,
) -> Any:
    document.ClearSelection()
    options = app.CreateStructImportOptions()
    try:
        layer.Import(str(reference_path), 0, options)
    except TypeError:
        layer.Import(str(reference_path))
    selected = document.SelectionRange
    if int(selected.Count) != 1:
        raise RuntimeError("Reference import did not produce exactly one selected bitmap.")
    shape = selected.Item(1)
    shape.Name = "REFERENCE_BITMAP_NONPRINTING"
    shape.SetSize(PAGE_WIDTH, PAGE_HEIGHT)
    shape.SetPosition(0.0, 0.0)
    return shape


def _shape_bounds(shape: Any) -> dict[str, float]:
    return {
        "left": float(shape.PositionX),
        "bottom": float(shape.PositionY),
        "right": float(shape.PositionX) + float(shape.SizeWidth),
        "top": float(shape.PositionY) + float(shape.SizeHeight),
    }


def _walk_shapes(shapes: Any) -> Iterable[Any]:
    for index in range(1, int(shapes.Count) + 1):
        shape = shapes.Item(index)
        yield shape
        if int(shape.Type) == 7:
            yield from _walk_shapes(shape.Shapes)
        try:
            contents = shape.PowerClip.Shapes
            if int(contents.Count):
                yield from _walk_shapes(contents)
        except Exception:
            pass


def _audit_document(document: Any, pattern_container: Any) -> dict[str, Any]:
    page = document.ActivePage
    layers = []
    counts = Counter()
    printable_bitmap_names: list[str] = []
    bounds_failures: list[dict[str, Any]] = []
    tolerance = 0.0005
    all_layers = page.AllLayers
    for index in range(1, int(all_layers.Count) + 1):
        layer = all_layers.Item(index)
        printable = bool(layer.Printable)
        layer_entry = {
            "name": str(layer.Name),
            "visible": bool(layer.Visible),
            "editable": bool(layer.Editable),
            "printable": printable,
            "top_level_shape_count": int(layer.Shapes.Count),
        }
        layers.append(layer_entry)
        for shape in _walk_shapes(layer.Shapes):
            shape_type = int(shape.Type)
            counts[shape_type] += 1
            if printable and shape_type == 5:
                printable_bitmap_names.append(str(shape.Name))
        if printable:
            for shape_index in range(1, int(layer.Shapes.Count) + 1):
                shape = layer.Shapes.Item(shape_index)
                bounds = _shape_bounds(shape)
                if (
                    bounds["left"] < -tolerance
                    or bounds["bottom"] < -tolerance
                    or bounds["right"] > PAGE_WIDTH + tolerance
                    or bounds["top"] > PAGE_HEIGHT + tolerance
                ):
                    bounds_failures.append({"name": str(shape.Name), "bounds_inches": bounds})
    try:
        powerclip_count = int(pattern_container.PowerClip.Shapes.Count)
    except Exception:
        powerclip_count = 0
    reference = next(item for item in layers if item["name"] == EXPECTED_LAYERS[0])
    return {
        "layers": layers,
        "expected_layers_present": all(name in {item["name"] for item in layers} for name in EXPECTED_LAYERS),
        "reference_layer_gate": {
            "hidden": not reference["visible"],
            "locked": not reference["editable"],
            "nonprinting": not reference["printable"],
            "passed": not reference["visible"] and not reference["editable"] and not reference["printable"],
        },
        "shape_type_counts": {str(key): value for key, value in sorted(counts.items())},
        "printable_bitmap_names": printable_bitmap_names,
        "contains_no_printable_bitmaps": not printable_bitmap_names,
        "powerclip_child_count": powerclip_count,
        "powerclip_verified": powerclip_count > 0,
        "printable_top_level_bounds_failures": bounds_failures,
        "all_printable_top_level_bounds_within_page": not bounds_failures,
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
        "Subject": "Alhamdulillah V2 measured structural trace",
    }
    applied: dict[str, Any] = {}
    unavailable: dict[str, str] = {}
    for property_name, value in requested.items():
        try:
            setattr(settings, property_name, value)
            applied[property_name] = getattr(settings, property_name)
        except Exception as exc:
            unavailable[property_name] = type(exc).__name__
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


def _render_comparison(
    document: Any,
    reference_path: Path,
    workspace: Path,
) -> dict[str, str]:
    from PIL import Image, ImageChops

    reference = Image.open(reference_path).convert("RGB")
    preview_path = workspace / "phase2_structure_preview.png"
    overlay_path = workspace / "phase2_structure_overlay_analysis.png"
    difference_path = workspace / "phase2_structure_difference_analysis.png"
    export_filter = document.ExportBitmap(
        str(preview_path),
        802,  # cdrPNG
        1,  # current page
        4,  # RGB
        reference.width,
        reference.height,
        round(reference.width / PAGE_WIDTH),
        round(reference.height / PAGE_HEIGHT),
        1,
        False,
        False,
        True,
        False,
        0,
        None,
        None,
    )
    export_filter.Finish()
    if not preview_path.is_file() or not preview_path.stat().st_size:
        raise RuntimeError("CorelDRAW did not create the Phase 2 PNG preview.")
    preview = Image.open(preview_path).convert("RGB").resize(reference.size)
    Image.blend(reference, preview, 0.5).save(overlay_path)
    ImageChops.difference(reference, preview).save(difference_path)
    return {
        "vector_preview": str(preview_path),
        "reference_overlay_analysis_only": str(overlay_path),
        "difference_analysis_only": str(difference_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    measurements, reference_path = _load_workspace(workspace)
    cdr_path = workspace / "Alhamdulillah_A4_Landscape_V2_Phase2_Structure.cdr"
    pdf_path = workspace / "Alhamdulillah_A4_Landscape_V2_Phase2_Structure.pdf"
    audit_path = workspace / "phase2_structure_audit.json"
    for path in (cdr_path, pdf_path, audit_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing Phase 2 artifact: {path}")

    point = _coordinate_mapper(measurements)
    trellis_point = _trellis_coordinate_mapper(point)
    field = _field_pixels(measurements)
    field_left, field_bottom = point(field["left_pixels"], field["bottom_pixels"])
    field_right, field_top = point(field["right_pixels"], field["top_pixels"])

    pythoncom.CoInitialize()
    bridge = CorelBridge()
    try:
        bridge.connect()
        bridge.create_document(PAGE_WIDTH, PAGE_HEIGHT)
        document = bridge.target_doc
        app = bridge.app
        if document is None or app is None:
            raise RuntimeError("CorelDRAW did not expose the Phase 2 document.")
        app.Visible = True
        page = document.ActivePage
        reference_layer = page.ActiveLayer
        reference_layer.Name = EXPECTED_LAYERS[0]

        with bridge._in_inches(document), bridge._reference_point(
            document, bridge.CDR_BOTTOM_LEFT
        ):
            _import_reference(app, document, reference_layer, reference_path)
            background_layer = page.CreateLayer(EXPECTED_LAYERS[1])
            trellis_layer = page.CreateLayer(EXPECTED_LAYERS[2])
            plaque_layer = page.CreateLayer(EXPECTED_LAYERS[3])
            page.CreateLayer(EXPECTED_LAYERS[4])
            page.CreateLayer(EXPECTED_LAYERS[5])
            page.CreateLayer(EXPECTED_LAYERS[6])

            page_background = background_layer.CreateRectangle2(
                0.0, 0.0, PAGE_WIDTH, PAGE_HEIGHT
            )
            page_background.Name = "A4_WHITE_PAGE"
            _uniform(page_background, app, "#FFFFFF")
            _no_outline(page_background)

            field_container = trellis_layer.CreateRectangle2(
                field_left,
                field_bottom,
                field_right - field_left,
                field_top - field_bottom,
            )
            field_container.Name = "Trellis_Field_PowerClip"
            _fountain(
                field_container,
                app,
                [(0, "#B77F60"), (48, "#D7B579"), (100, "#F0DFA9")],
                angle=285.0,
            )
            _no_outline(field_container)

            pattern_shapes: list[Any] = []
            image = measurements["rectified_image"]
            width = int(image["width_pixels"])
            height = int(image["height_pixels"])
            y = TRELLIS_ORIGIN_Y_PX - TRELLIS_PITCH_Y_PX
            while y <= height + TRELLIS_PITCH_Y_PX:
                x = TRELLIS_ORIGIN_X_PX - TRELLIS_PITCH_X_PX
                while x <= width + TRELLIS_PITCH_X_PX:
                    motif = _curve_shape(
                        app,
                        document,
                        trellis_layer,
                        f"Trellis_Motif_{len(pattern_shapes) + 1:03d}",
                        _mapped_commands(trellis_point, _motif_commands(x, y)),
                    )
                    _no_fill(motif)
                    _outline(motif, app, "#49393A", 0.0190)
                    pattern_shapes.append(motif)
                    x += TRELLIS_PITCH_X_PX
                y += TRELLIS_PITCH_Y_PX
            pattern_group = _group(app, pattern_shapes, "Measured_Trellis_Repeat_Field")
            pattern_group.AddToPowerClip(field_container, 0)

            plaque = _curve_shape(
                app,
                document,
                plaque_layer,
                "Traced_Plaque_Silhouette",
                _mapped_commands(point, _plaque_commands(field)),
            )
            _fountain(
                plaque,
                app,
                [(0, "#513730"), (45, "#3D2B29"), (100, "#262425")],
                angle=90.0,
            )
            _no_outline(plaque)

        reference_layer.Printable = False
        reference_layer.Visible = False
        reference_layer.Editable = False
        document.ClearSelection()

        document_audit = _audit_document(document, field_container)
        if not document_audit["reference_layer_gate"]["passed"]:
            raise RuntimeError("Reference layer is not hidden, locked, and nonprinting.")
        if not document_audit["contains_no_printable_bitmaps"]:
            raise RuntimeError("A printable bitmap was detected in the Phase 2 document.")
        if not document_audit["powerclip_verified"]:
            raise RuntimeError("CorelDRAW did not retain trellis PowerClip contents.")
        if not document_audit["all_printable_top_level_bounds_within_page"]:
            raise RuntimeError("At least one printable top-level object extends outside A4.")

        pdf_settings = _configure_pdf(document)
        bridge.save_document(str(cdr_path))
        document.PublishToPDF(str(pdf_path))
        if not pdf_path.is_file() or not pdf_path.stat().st_size:
            raise RuntimeError("CorelDRAW did not create the Phase 2 PDF.")
        pdf_audit = _pdf_audit(pdf_path)
        if pdf_audit["embedded_image_objects"]:
            raise RuntimeError("The nonprinting reference unexpectedly appeared as a PDF image.")
        comparison = _render_comparison(document, reference_path, workspace)

        audit = {
            "result": "PASS_PHASE2_STRUCTURE",
            "scope": (
                "Vector integrity and containment for the Phase 2 structure; "
                "visual fidelity is not evaluated by this audit"
            ),
            "source_sha256": measurements["source_preflight"]["sha256"],
            "measurement_schema": measurements["schema_version"],
            "page": measurements["page"],
            "inner_printed_field": measurements["inner_printed_field"],
            "page_corner_extrapolation": measurements["page_quadrilateral"],
            "document_audit": document_audit,
            "pdf_settings": pdf_settings,
            "pdf_audit": pdf_audit,
            "artifacts": {
                "working_cdr": str(cdr_path),
                "vector_pdf": str(pdf_path),
                **comparison,
            },
            "phase2_visual_gate": {
                "evaluated": False,
                "passed": False,
                "validator": "scripts/validate_alhamdulillah_v2_phase2.py",
            },
            "next_gate": (
                "Run the independent Phase 2 geometry validator and correct any "
                "field, plaque, or trellis mismatch before Arabic tracing."
            ),
        }
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            app.ActiveWindow.ActiveView.ToFitPage()
        except Exception:
            pass
        print(
            json.dumps(
                {
                    "result": audit["result"],
                    "cdr": str(cdr_path),
                    "pdf": str(pdf_path),
                    "preview": comparison["vector_preview"],
                    "powerclip_children": document_audit["powerclip_child_count"],
                    "printable_bitmaps": document_audit["printable_bitmap_names"],
                    "bounds_failures": document_audit["printable_top_level_bounds_failures"],
                    "pdf_images": pdf_audit["embedded_image_objects"],
                },
                indent=2,
            )
        )
        return 0
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
