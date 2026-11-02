"""Trace a retained Arabic silhouette into native CorelDRAW X7 curves.

This Phase 3 builder is deliberately non-overwriting.  It opens the exact CDR
that passed the independent Phase 2 gate, adds only measured curve geometry to
the prepared Arabic layer, and saves a separately named CDR/PDF in a new run
directory.  The photographed reference and analysis masks remain nonprinting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import pythoncom
from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corel_operator.calligraphy_tracing import (  # noqa: E402
    MaskComponent,
    TracedComponent,
    connected_components,
    filtered_mask,
    mask_metrics,
    trace_components,
    trace_summary,
)
from corel_operator.corel_bridge import CorelBridge  # noqa: E402
from scripts.build_alhamdulillah_v2_structure import (  # noqa: E402
    EXPECTED_LAYERS,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    _audit_document,
    _configure_pdf,
    _coordinate_mapper,
    _curve_shape,
    _fountain,
    _group,
    _no_outline,
    _pdf_audit,
)


ARABIC_LAYER = "04 - Arabic Calligraphy Curves"
PHASE2_CDR = "Alhamdulillah_A4_Landscape_V2_Phase2_Structure.cdr"
PHASE2_GATE = "phase2_geometry_validation.json"
MINIMUM_COMPONENT_AREA = 100
PRINCIPAL_COMPONENT_AREA = 1500
SIMPLIFY_TOLERANCE_PIXELS = 1.0
MINIMUM_SILHOUETTE_IOU = 0.93


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_inputs(
    workspace: Path,
    mask_path: Path,
    run_name: str,
) -> tuple[dict[str, Any], Path, Path, Path]:
    gate_path = workspace / PHASE2_GATE
    source_cdr = workspace / PHASE2_CDR
    measurements_path = workspace / "v2_measurements.json"
    manifest_path = workspace / "V2_WORKSPACE_MANIFEST.json"
    for path in (gate_path, source_cdr, measurements_path, manifest_path, mask_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required Phase 3 input is missing: {path}")
    gate = _load_json(gate_path)
    if gate.get("result") != "PASS_PHASE2_GATE":
        raise ValueError("Arabic tracing requires a retained PASS_PHASE2_GATE report.")
    if not gate.get("validation_scope", {}).get("arabic_tracing_authorized"):
        raise ValueError("The Phase 2 report does not authorize Arabic tracing.")
    expected_cdr_hash = gate["artifact_integrity"]["retained_input_fingerprints"]["cdr"]["sha256"]
    if _sha256(source_cdr) != expected_cdr_hash:
        raise ValueError("The Phase 2 CDR bytes no longer match the passing gate report.")
    measurements = _load_json(measurements_path)
    expected_size = (
        int(measurements["rectified_image"]["width_pixels"]),
        int(measurements["rectified_image"]["height_pixels"]),
    )
    with Image.open(mask_path) as mask:
        if mask.size != expected_size:
            raise ValueError(f"Arabic mask size {mask.size!r} does not match {expected_size!r}.")
    run_dir = workspace / run_name
    if run_dir.exists():
        raise FileExistsError(f"Refusing to reuse Phase 3 run directory: {run_dir}")
    return measurements, source_cdr, gate_path, run_dir


def _find_layer(page: Any, name: str) -> Any:
    layers = page.AllLayers
    for index in range(1, int(layers.Count) + 1):
        layer = layers.Item(index)
        if str(layer.Name) == name:
            return layer
    raise ValueError(f"Required CorelDRAW layer is missing: {name}")


def _find_shape(layer: Any, name: str) -> Any:
    for index in range(1, int(layer.Shapes.Count) + 1):
        shape = layer.Shapes.Item(index)
        if str(shape.Name) == name:
            return shape
    raise ValueError(f"Required CorelDRAW shape is missing: {name}")


def _component_commands(
    trace: TracedComponent,
    point: Any,
) -> Iterable[tuple[Any, ...]]:
    for loop in trace.loops:
        start_x, start_y = point(*loop[0])
        yield ("M", start_x, start_y)
        for pixel_x, pixel_y in loop[1:]:
            x, y = point(pixel_x, pixel_y)
            yield ("L", x, y)
        yield ("Z",)


def _component_name(trace: TracedComponent, role_number: int) -> str:
    if trace.role == "main_connected_composition":
        return "Arabic_Main_Connected_Composition"
    if trace.role == "detached_principal_stroke":
        return f"Arabic_Detached_Principal_Stroke_{role_number:02d}"
    return f"Arabic_Diacritic_or_Detached_Mark_{role_number:02d}"


def _export_page(
    document: Any,
    path: Path,
    width: int,
    height: int,
) -> None:
    export_filter = document.ExportBitmap(
        str(path),
        802,  # cdrPNG
        1,  # current page
        4,  # RGB
        width,
        height,
        round(width / PAGE_WIDTH),
        round(height / PAGE_HEIGHT),
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
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError(f"CorelDRAW did not create the expected preview: {path}")


def _difference_silhouette(
    baseline: Image.Image,
    candidate: Image.Image,
    minimum_channel_difference: int = 12,
) -> tuple[Image.Image, Image.Image]:
    """Isolate newly rendered artwork without toggling fragile X7 layer states."""

    left = baseline.convert("RGB")
    right = candidate.convert("RGB")
    if left.size != right.size:
        raise ValueError(f"Preview dimensions differ: {left.size!r} != {right.size!r}")
    difference = ImageChops.difference(left, right)
    output = Image.new("L", left.size, 0)
    output.putdata(
        [
            255 if max(red, green, blue) >= minimum_channel_difference else 0
            for red, green, blue in difference.get_flattened_data()
        ]
    )
    return difference, output


def _save_mask_comparison(
    expected: Image.Image,
    actual: Image.Image,
    overlay_path: Path,
    difference_path: Path,
) -> None:
    expected = expected.convert("L")
    actual = actual.convert("L")
    red = Image.new("L", expected.size, 0)
    green = ImageChops.multiply(expected, actual)
    blue = Image.new("L", expected.size, 0)
    expected_only = ImageChops.subtract(expected, actual)
    actual_only = ImageChops.subtract(actual, expected)
    red = ImageChops.lighter(green, expected_only)
    blue = ImageChops.lighter(green, actual_only)
    Image.merge("RGB", (red, green, blue)).save(overlay_path)
    ImageChops.logical_xor(expected.convert("1"), actual.convert("1")).convert("L").save(
        difference_path
    )


def _shape_inventory(shapes: Any) -> dict[str, int]:
    inventory = {"groups": 0, "curves": 0, "text": 0, "bitmaps": 0, "other": 0}
    for index in range(1, int(shapes.Count) + 1):
        shape = shapes.Item(index)
        shape_type = int(shape.Type)
        key = {7: "groups", 3: "curves", 6: "text", 5: "bitmaps"}.get(shape_type, "other")
        inventory[key] += 1
        if shape_type == 7:
            child = _shape_inventory(shape.Shapes)
            for child_key, count in child.items():
                inventory[child_key] += count
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--run-name", default="phase3_arabic_trace01")
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    mask_path = args.mask.expanduser().resolve()
    measurements, source_cdr, gate_path, run_dir = _validate_inputs(
        workspace, mask_path, args.run_name
    )
    source_cdr_hash = _sha256(source_cdr)
    reference_path = workspace / "00_reference_nonprinting" / "reference_rectified_a4.png"
    phase2_preview_path = workspace / "phase2_structure_preview.png"
    for path in (reference_path, phase2_preview_path):
        if not path.is_file():
            raise FileNotFoundError(f"Retained Phase 2 image is missing: {path}")

    measured_mask = Image.open(mask_path).convert("L")
    components: list[MaskComponent] = connected_components(
        measured_mask,
        minimum_area=MINIMUM_COMPONENT_AREA,
    )
    if not components:
        raise ValueError("The measured Arabic mask has no retained components.")
    traces = trace_components(
        components,
        simplify_tolerance=SIMPLIFY_TOLERANCE_PIXELS,
        principal_area=PRINCIPAL_COMPONENT_AREA,
    )
    expected_mask = filtered_mask(measured_mask.size, components)
    width, height = measured_mask.size

    run_dir.mkdir(parents=False, exist_ok=False)
    cdr_path = run_dir / "Alhamdulillah_A4_Landscape_V2_Phase3_Arabic_Trace.cdr"
    pdf_path = run_dir / "Alhamdulillah_A4_Landscape_V2_Phase3_Arabic_Trace.pdf"
    full_preview_path = run_dir / "phase3_full_preview.png"
    full_overlay_path = run_dir / "phase3_full_overlay_analysis.png"
    arabic_difference_path = run_dir / "phase3_arabic_render_difference.png"
    expected_mask_path = run_dir / "phase3_arabic_expected_mask_analysis.png"
    actual_mask_path = run_dir / "phase3_arabic_vector_mask_analysis.png"
    mask_overlay_path = run_dir / "phase3_arabic_mask_overlay_analysis.png"
    mask_difference_path = run_dir / "phase3_arabic_mask_difference_analysis.png"
    audit_path = run_dir / "phase3_calligraphy_audit.json"
    expected_mask.save(expected_mask_path)

    pythoncom.CoInitialize()
    bridge = CorelBridge()
    try:
        bridge.connect()
        app = bridge.app
        if app is None:
            raise RuntimeError("CorelDRAW application was not exposed after connection.")
        app.Visible = True
        document = app.OpenDocument(str(source_cdr))
        bridge.target_doc = document
        page = document.ActivePage
        arabic_layer = _find_layer(page, ARABIC_LAYER)
        trellis_layer = _find_layer(page, EXPECTED_LAYERS[2])
        pattern_container = _find_shape(trellis_layer, "Trellis_Field_PowerClip")
        if int(arabic_layer.Shapes.Count):
            raise ValueError("The Phase 2 Arabic layer is not empty; refusing to add a second trace.")

        point = _coordinate_mapper(measurements)
        arabic_layer.Visible = True
        arabic_layer.Editable = True
        arabic_layer.Printable = True
        principal_shapes: list[Any] = []
        mark_shapes: list[Any] = []
        principal_number = mark_number = 0
        with bridge._in_inches(document), bridge._reference_point(
            document, bridge.CDR_BOTTOM_LEFT
        ):
            for trace in traces:
                if trace.role == "diacritic_or_detached_mark":
                    mark_number += 1
                    number = mark_number
                else:
                    principal_number += 1
                    number = principal_number
                shape = _curve_shape(
                    app,
                    document,
                    arabic_layer,
                    _component_name(trace, number),
                    _component_commands(trace, point),
                )
                _fountain(
                    shape,
                    app,
                    [(0, "#794319"), (38, "#DDAF55"), (58, "#FFF0B0"), (100, "#A86422")],
                    angle=88.0,
                )
                _no_outline(shape)
                if trace.role == "diacritic_or_detached_mark":
                    mark_shapes.append(shape)
                else:
                    principal_shapes.append(shape)

            principal_group = _group(app, principal_shapes, "Arabic_Principal_Strokes")
            groups = [principal_group]
            if mark_shapes:
                groups.append(
                    _group(app, mark_shapes, "Arabic_Detached_Marks_and_Diacritics")
                )
            composition = _group(app, groups, "Arabic_Calligraphy_Traced_Composition")
            composition.Name = "Arabic_Calligraphy_Traced_Composition"

        document.ClearSelection()
        full_preview_path.parent.mkdir(parents=True, exist_ok=True)
        _export_page(document, full_preview_path, width, height)

        reference = Image.open(reference_path).convert("RGB")
        full_preview = Image.open(full_preview_path).convert("RGB").resize(reference.size)
        Image.blend(reference, full_preview, 0.5).save(full_overlay_path)
        phase2_preview = Image.open(phase2_preview_path).convert("RGB")
        arabic_difference, actual_mask = _difference_silhouette(
            phase2_preview,
            full_preview,
        )
        arabic_difference.save(arabic_difference_path)
        actual_mask.save(actual_mask_path)
        silhouette_metrics = mask_metrics(expected_mask, actual_mask)
        _save_mask_comparison(
            expected_mask,
            actual_mask,
            mask_overlay_path,
            mask_difference_path,
        )

        with bridge._in_inches(document), bridge._reference_point(
            document, bridge.CDR_BOTTOM_LEFT
        ):
            document_audit = _audit_document(document, pattern_container)
        arabic_inventory = _shape_inventory(arabic_layer.Shapes)
        vector_gate = (
            document_audit["reference_layer_gate"]["passed"]
            and document_audit["contains_no_printable_bitmaps"]
            and document_audit["powerclip_verified"]
            and document_audit["all_printable_top_level_bounds_within_page"]
            and arabic_inventory["curves"] == len(traces)
            and arabic_inventory["text"] == 0
            and arabic_inventory["bitmaps"] == 0
        )
        silhouette_gate = silhouette_metrics["iou"] >= MINIMUM_SILHOUETTE_IOU

        pdf_settings = _configure_pdf(document)
        document.PublishToPDF(str(pdf_path))
        if not pdf_path.is_file() or not pdf_path.stat().st_size:
            raise RuntimeError("CorelDRAW did not create the Phase 3 PDF.")
        pdf_audit = _pdf_audit(pdf_path)
        if pdf_audit["embedded_image_objects"]:
            raise RuntimeError("The nonprinting reference unexpectedly appeared in the PDF.")
        bridge.save_document(str(cdr_path))

        source_preserved = _sha256(source_cdr) == source_cdr_hash
        passed = vector_gate and silhouette_gate and source_preserved
        audit = {
            "schema_version": "alhamdulillah-phase3-calligraphy-audit-v1",
            "result": (
                "PASS_PHASE3_AUTOMATED_GATE_REVIEW_REQUIRED"
                if passed
                else "FAIL_PHASE3_AUTOMATED_GATE"
            ),
            "scope": (
                "Measured Arabic silhouette, native-curve integrity, source preservation, "
                "and strict raster overlap; manual reading and 50-percent overlay review remain required"
            ),
            "phase2_input": {
                "workspace": str(workspace),
                "gate_report": str(gate_path),
                "source_cdr": str(source_cdr),
                "source_cdr_sha256_before": source_cdr_hash,
                "source_cdr_sha256_after": _sha256(source_cdr),
                "source_cdr_preserved": source_preserved,
            },
            "measured_mask": {
                "path": str(mask_path),
                "sha256": _sha256(mask_path),
                "dimensions_pixels": [width, height],
                "foreground_pixels_before_noise_filter": measured_mask.histogram()[255],
                "minimum_component_area_pixels": MINIMUM_COMPONENT_AREA,
                "foreground_pixels_retained": expected_mask.histogram()[255],
            },
            "trace": {
                "visible_arabic_uses_font": False,
                "visible_arabic_object_kind": "native CorelDRAW curves",
                "simplify_tolerance_pixels": SIMPLIFY_TOLERANCE_PIXELS,
                "principal_component_area_pixels": PRINCIPAL_COMPONENT_AREA,
                **trace_summary(traces),
            },
            "silhouette_validation": {
                **silhouette_metrics,
                "minimum_iou": MINIMUM_SILHOUETTE_IOU,
                "passed": silhouette_gate,
            },
            "vector_integrity": {
                "arabic_layer_inventory": arabic_inventory,
                "document_audit": document_audit,
                "pdf_settings": pdf_settings,
                "pdf_audit": pdf_audit,
                "passed": vector_gate,
            },
            "manual_review": {
                "required": True,
                "completed": False,
                "checks": [
                    "Confirm the visible reading is الحمد لله against the rectified source.",
                    "Inspect the 50-percent full overlay for stroke terminals and negative spaces.",
                    "Confirm retained detached marks are calligraphic elements rather than glare or trellis noise.",
                ],
            },
            "artifacts": {
                "editable_cdr": str(cdr_path),
                "vector_pdf": str(pdf_path),
                "full_preview": str(full_preview_path),
                "full_overlay_analysis_only": str(full_overlay_path),
                "arabic_render_difference": str(arabic_difference_path),
                "expected_mask_analysis_only": str(expected_mask_path),
                "actual_mask_analysis_only": str(actual_mask_path),
                "mask_overlay_analysis_only": str(mask_overlay_path),
                "mask_difference_analysis_only": str(mask_difference_path),
            },
            "next_action": (
                "Perform the required manual overlay/reading review before authorizing English typography."
                if passed
                else "Correct only the failing Phase 3 trace and retain a new non-overwriting run."
            ),
        }
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "result": audit["result"],
            "run_directory": str(run_dir),
            "silhouette_iou": round(float(silhouette_metrics["iou"]), 6),
            "curve_components": arabic_inventory["curves"],
            "text_objects": arabic_inventory["text"],
            "printable_bitmaps": document_audit["printable_bitmap_names"],
            "source_phase2_preserved": source_preserved,
            "manual_review_required": True,
        }, indent=2))
        return 0 if passed else 2
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
