"""Independent raster geometry checks for the Alhamdulillah V2 Phase 2 gate.

The CorelDRAW build audit proves vector integrity.  This module deliberately
uses only retained PNG/JSON files so that visual fidelity is a separate gate.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageFilter, UnidentifiedImageError


PAGE_WIDTH_MM = 297.0
PAGE_HEIGHT_MM = 210.0
PLAQUE_IOU_MINIMUM = 0.97
GEOMETRY_TOLERANCE_MM = 0.5
PATTERN_PRECISION_MINIMUM = 0.80
PATTERN_RECALL_MINIMUM = 0.65


class Phase2ValidationError(ValueError):
    """Raised when retained Phase 2 evidence cannot be validated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_fingerprints(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Bind a report to the exact retained inputs that it evaluated."""
    return {
        name: {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for name, path in paths.items()
    }


def _unevaluated_geometry(reason: str) -> dict[str, Any]:
    return {
        "evaluated": False,
        "reason": reason,
        "maximum_edge_error_mm": None,
        "iou": None,
        "tolerant_f1": None,
        "passed": False,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2ValidationError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Phase2ValidationError(f"Expected a JSON object in {path}.")
    return value


def _threshold(image: Image.Image, cutoff: int) -> Image.Image:
    return image.point(lambda value: 255 if value >= cutoff else 0, mode="1").convert("L")


def _count_mask(mask: Image.Image) -> int:
    return int(mask.histogram()[255])


def _median(values: list[int], radius: int = 2) -> list[int]:
    result: list[int] = []
    for index in range(len(values)):
        window = values[max(0, index - radius) : min(len(values), index + radius + 1)]
        result.append(sorted(window)[len(window) // 2])
    return result


def _rendered_field_bounds(preview: Image.Image) -> tuple[int, int, int, int]:
    white = Image.new("RGB", preview.size, "white")
    difference = ImageChops.difference(preview.convert("RGB"), white).convert("L")
    bounds = _threshold(difference, 6).getbbox()
    if bounds is None:
        raise Phase2ValidationError("The retained preview contains no non-white artwork.")
    return bounds


def _expected_field_bounds(
    measurements: dict[str, Any], width: int, height: int
) -> tuple[float, float, float, float]:
    bounds = measurements["inner_printed_field"]["average_bounds_mm"]
    return (
        float(bounds["left"]) / PAGE_WIDTH_MM * width,
        (PAGE_HEIGHT_MM - float(bounds["top"])) / PAGE_HEIGHT_MM * height,
        float(bounds["right"]) / PAGE_WIDTH_MM * width,
        (PAGE_HEIGHT_MM - float(bounds["bottom"])) / PAGE_HEIGHT_MM * height,
    )


def _preview_plaque_boundaries(
    preview: Image.Image, field: tuple[int, int, int, int]
) -> tuple[list[int], list[int]]:
    """Find filled plaque bounds; a box blur rejects the thin trellis strokes."""
    left, top, right, bottom = field
    smooth = preview.convert("L").filter(ImageFilter.BoxBlur(4))
    pixels = smooth.load()
    upper_limit = min(bottom - 1, top + round(preview.height * 0.34))
    lower_start = max(top, round(preview.height * 0.55))
    tops: list[int] = []
    bottoms: list[int] = []
    for x in range(left, right):
        candidates = [y for y in range(top, upper_limit + 1) if pixels[x, y] < 100]
        tops.append(candidates[0] if candidates else upper_limit)
        candidates = [y for y in range(lower_start, bottom) if pixels[x, y] < 110]
        bottoms.append(candidates[-1] if candidates else lower_start)
    return _median(tops), _median(bottoms)


def _matched_reference_boundaries(
    reference: Image.Image,
    field: tuple[int, int, int, int],
    preview_top: list[int],
    preview_bottom: list[int],
    search_radius: int = 24,
) -> tuple[list[int], list[int], list[float], list[float]]:
    """Match the candidate plaque edges to nearby sustained photo edges."""
    left, field_top, right, field_bottom = field
    smooth = reference.convert("L").filter(ImageFilter.GaussianBlur(2.2))
    pixels = smooth.load()
    reference_top: list[int] = []
    reference_bottom: list[int] = []
    top_strengths: list[float] = []
    bottom_strengths: list[float] = []
    for offset, x in enumerate(range(left, right)):
        top_center = preview_top[offset]
        top_candidates: list[tuple[float, int]] = []
        for y in range(
            max(field_top, top_center - search_radius),
            min(field_bottom - 4, top_center + search_radius) + 1,
        ):
            top_candidates.append((float(pixels[x, y - 3]) - float(pixels[x, y + 3]), y))
        top_strength, top_y = max(top_candidates)
        reference_top.append(top_y)
        top_strengths.append(top_strength)

        bottom_center = preview_bottom[offset]
        bottom_candidates: list[tuple[float, int]] = []
        for y in range(
            max(field_top + 3, bottom_center - search_radius),
            min(field_bottom - 4, bottom_center + search_radius) + 1,
        ):
            bottom_candidates.append((float(pixels[x, y + 3]) - float(pixels[x, y - 3]), y))
        bottom_strength, bottom_y = max(bottom_candidates)
        reference_bottom.append(bottom_y)
        bottom_strengths.append(bottom_strength)
    return (
        _median(reference_top),
        _median(reference_bottom),
        top_strengths,
        bottom_strengths,
    )


def _plaque_metrics(
    reference: Image.Image,
    preview: Image.Image,
    field: tuple[int, int, int, int],
) -> tuple[dict[str, Any], tuple[list[int], list[int]]]:
    preview_top, preview_bottom = _preview_plaque_boundaries(preview, field)
    reference_top, reference_bottom, top_strengths, bottom_strengths = (
        _matched_reference_boundaries(
            reference, field, preview_top, preview_bottom
        )
    )
    intersection = 0
    union = 0
    displacements: list[int] = []
    for pt, pb, rt, rb in zip(
        preview_top, preview_bottom, reference_top, reference_bottom
    ):
        intersection += max(0, min(pb, rb) - max(pt, rt) + 1)
        union += max(pb, rb) - min(pt, rt) + 1
        displacements.extend((abs(pt - rt), abs(pb - rb)))
    ordered = sorted(displacements)
    p95 = ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)]
    mm_per_pixel = PAGE_WIDTH_MM / preview.width
    confidence_cutoff = 8.0
    confidence = sum(value >= confidence_cutoff for value in top_strengths + bottom_strengths)
    confidence /= len(top_strengths) + len(bottom_strengths)
    iou = intersection / union if union else 0.0
    metrics = {
        "evaluated": True,
        "method": "candidate edge matched to Gaussian-smoothed reference within 24 px",
        "intersection_pixels": intersection,
        "union_pixels": union,
        "iou": round(iou, 6),
        "minimum_iou": PLAQUE_IOU_MINIMUM,
        "mean_boundary_error_mm": round(
            sum(displacements) / len(displacements) * mm_per_pixel, 4
        ),
        "p95_boundary_error_mm": round(p95 * mm_per_pixel, 4),
        "edge_match_confidence": round(confidence, 6),
        "passed": iou >= PLAQUE_IOU_MINIMUM and confidence >= 0.90,
    }
    return metrics, (preview_top, preview_bottom)


def _pattern_region(
    size: tuple[int, int],
    field: tuple[int, int, int, int],
    plaque: tuple[list[int], list[int]],
    inset: int = 5,
) -> Image.Image:
    left, top, right, bottom = field
    plaque_top, plaque_bottom = plaque
    region = Image.new("L", size, 0)
    pixels = region.load()
    for offset, x in enumerate(range(left + inset, right - inset)):
        source_offset = offset + inset
        for y in range(top + inset, max(top + inset, plaque_top[source_offset] - inset)):
            pixels[x, y] = 255
        for y in range(
            min(bottom - inset, plaque_bottom[source_offset] + inset + 1), bottom - inset
        ):
            pixels[x, y] = 255
    return region


def _dark_line_mask(image: Image.Image, region: Image.Image, cutoff: int) -> Image.Image:
    gray = image.convert("L")
    local_average = gray.filter(ImageFilter.GaussianBlur(3.0))
    response = ImageChops.subtract(local_average, gray)
    return ImageChops.multiply(_threshold(response, cutoff), region)


def _pattern_metrics(
    reference: Image.Image,
    preview: Image.Image,
    field: tuple[int, int, int, int],
    plaque: tuple[list[int], list[int]],
) -> tuple[dict[str, Any], tuple[Image.Image, Image.Image, Image.Image]]:
    region = _pattern_region(preview.size, field, plaque)
    reference_edges = _dark_line_mask(reference, region, 14)
    preview_edges = _dark_line_mask(preview, region, 14)
    tolerance_pixels = max(
        1, round(GEOMETRY_TOLERANCE_MM / (PAGE_WIDTH_MM / preview.width))
    )
    filter_size = tolerance_pixels * 2 + 1
    expanded_reference = reference_edges.filter(ImageFilter.MaxFilter(filter_size))
    expanded_preview = preview_edges.filter(ImageFilter.MaxFilter(filter_size))
    preview_count = _count_mask(preview_edges)
    reference_count = _count_mask(reference_edges)
    matched_preview = _count_mask(ImageChops.multiply(preview_edges, expanded_reference))
    matched_reference = _count_mask(ImageChops.multiply(reference_edges, expanded_preview))
    precision = matched_preview / preview_count if preview_count else 0.0
    recall = matched_reference / reference_count if reference_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    metrics = {
        "evaluated": True,
        "method": "local dark-line response compared inside visible trellis regions",
        "line_response_cutoff": 14,
        "tolerance_mm": GEOMETRY_TOLERANCE_MM,
        "tolerance_pixels": tolerance_pixels,
        "preview_edge_pixels": preview_count,
        "reference_edge_pixels": reference_count,
        "preview_edges_near_reference_fraction": round(precision, 6),
        "minimum_preview_fraction": PATTERN_PRECISION_MINIMUM,
        "reference_edges_near_preview_fraction": round(recall, 6),
        "minimum_reference_fraction": PATTERN_RECALL_MINIMUM,
        "tolerant_f1": round(f1, 6),
        "passed": (
            precision >= PATTERN_PRECISION_MINIMUM
            and recall >= PATTERN_RECALL_MINIMUM
        ),
    }
    return metrics, (region, reference_edges, preview_edges)


def _field_metrics(
    measurements: dict[str, Any], preview: Image.Image
) -> tuple[dict[str, Any], tuple[int, int, int, int]]:
    rendered = _rendered_field_bounds(preview)
    expected = _expected_field_bounds(measurements, *preview.size)
    mm_per_x = PAGE_WIDTH_MM / preview.width
    mm_per_y = PAGE_HEIGHT_MM / preview.height
    errors = {
        "left": abs(rendered[0] - expected[0]) * mm_per_x,
        "top": abs(rendered[1] - expected[1]) * mm_per_y,
        "right": abs(rendered[2] - expected[2]) * mm_per_x,
        "bottom": abs(rendered[3] - expected[3]) * mm_per_y,
    }
    maximum = max(errors.values())
    return (
        {
            "evaluated": True,
            "expected_bounds_pixels": [round(value, 3) for value in expected],
            "rendered_bounds_pixels": list(rendered),
            "edge_errors_mm": {key: round(value, 4) for key, value in errors.items()},
            "maximum_edge_error_mm": round(maximum, 4),
            "tolerance_mm": GEOMETRY_TOLERANCE_MM,
            "passed": maximum <= GEOMETRY_TOLERANCE_MM,
        },
        rendered,
    )


def _required_artifacts(workspace: Path) -> dict[str, Path]:
    return {
        "manifest": workspace / "V2_WORKSPACE_MANIFEST.json",
        "measurements": workspace / "v2_measurements.json",
        "build_audit": workspace / "phase2_structure_audit.json",
        "reference": workspace / "00_reference_nonprinting" / "reference_rectified_a4.png",
        "preview": workspace / "phase2_structure_preview.png",
        "overlay": workspace / "phase2_structure_overlay_analysis.png",
        "difference": workspace / "phase2_structure_difference_analysis.png",
        "cdr": workspace / "Alhamdulillah_A4_Landscape_V2_Phase2_Structure.cdr",
        "pdf": workspace / "Alhamdulillah_A4_Landscape_V2_Phase2_Structure.pdf",
    }


def validate_phase2_workspace(workspace: Path) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    paths = _required_artifacts(workspace)
    missing = [name for name, path in paths.items() if not path.is_file() or not path.stat().st_size]
    if missing:
        raise Phase2ValidationError(f"Missing or empty retained artifacts: {', '.join(missing)}")

    manifest = _load_json(paths["manifest"])
    measurements = _load_json(paths["measurements"])
    build_audit = _load_json(paths["build_audit"])
    try:
        expected_size = (
            int(measurements["rectified_image"]["width_pixels"]),
            int(measurements["rectified_image"]["height_pixels"]),
        )
        expected_source_hash = str(measurements["source_preflight"]["sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Phase2ValidationError(
            "The measurement record lacks valid rectified dimensions or source identity."
        ) from exc
    if min(expected_size) <= 0:
        raise Phase2ValidationError("The expected rectified image dimensions must be positive.")
    try:
        with Image.open(paths["reference"]) as image:
            reference = image.convert("RGB")
        with Image.open(paths["preview"]) as image:
            preview = image.convert("RGB")
    except (OSError, UnidentifiedImageError) as exc:
        raise Phase2ValidationError(f"Cannot decode retained reference or preview PNG: {exc}") from exc

    dimensions_pass = reference.size == preview.size == expected_size
    if dimensions_pass:
        try:
            field, rendered_field = _field_metrics(measurements, preview)
            plaque, plaque_boundaries = _plaque_metrics(
                reference, preview, rendered_field
            )
            pattern, _diagnostics = _pattern_metrics(
                reference, preview, rendered_field, plaque_boundaries
            )
        except Phase2ValidationError:
            raise
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise Phase2ValidationError(f"Cannot evaluate retained geometry: {exc}") from exc
    else:
        reason = "Reference, preview, and calibrated dimensions are not identical."
        field = _unevaluated_geometry(reason)
        plaque = _unevaluated_geometry(reason)
        pattern = _unevaluated_geometry(reason)

    source_copy = workspace / "00_reference_nonprinting" / "source_original.jpeg"
    manifest_source = manifest.get("source_copy")
    manifest_hash = manifest_source.get("sha256") if isinstance(manifest_source, dict) else None
    source_copy_hash = _sha256(source_copy) if source_copy.is_file() else None
    source_hash_pass = (
        source_copy_hash == expected_source_hash
        and str(build_audit.get("source_sha256")) == expected_source_hash
        and str(manifest_hash) == expected_source_hash
    )
    document_audit = build_audit.get("document_audit")
    document_audit = document_audit if isinstance(document_audit, dict) else {}
    reference_gate = document_audit.get("reference_layer_gate")
    reference_gate = reference_gate if isinstance(reference_gate, dict) else {}
    pdf_audit = build_audit.get("pdf_audit")
    pdf_audit = pdf_audit if isinstance(pdf_audit, dict) else {}
    vector_checks = {
        "structure_result": build_audit.get("result") == "PASS_PHASE2_STRUCTURE",
        "reference_layer_gate": reference_gate.get("passed") is True,
        "no_printable_bitmaps": document_audit.get("contains_no_printable_bitmaps") is True,
        "powerclip_verified": document_audit.get("powerclip_verified") is True,
        "top_level_bounds_within_page": (
            document_audit.get("all_printable_top_level_bounds_within_page") is True
        ),
        "pdf_contains_no_images": pdf_audit.get("embedded_image_objects") == 0,
    }
    vector_gate = all(vector_checks.values())
    checks = {
        "required_artifacts": True,
        "source_identity": source_hash_pass,
        "image_dimensions": dimensions_pass,
        "vector_integrity_build_audit": vector_gate,
        "field_geometry": field["passed"],
        "plaque_geometry": plaque["passed"],
        "trellis_geometry": pattern["passed"],
    }
    blockers = [name for name, passed in checks.items() if not passed]
    passed = not blockers
    fingerprint_paths = dict(paths)
    if source_copy.is_file():
        fingerprint_paths["source_copy"] = source_copy
    return {
        "schema_version": "alhamdulillah-phase2-geometry-validation-v2",
        "result": "PASS_PHASE2_GATE" if passed else "FAIL_PHASE2_GATE",
        "workspace": str(workspace),
        "validation_scope": {
            "structure_audit": "vector integrity and containment only",
            "independent_gate": "field, plaque, and visible-trellis raster geometry",
            "arabic_tracing_authorized": passed,
        },
        "checks": checks,
        "artifact_integrity": {
            "source_sha256": expected_source_hash,
            "source_copy_sha256": source_copy_hash,
            "source_identity_passed": source_hash_pass,
            "reference_size_pixels": list(reference.size),
            "preview_size_pixels": list(preview.size),
            "expected_size_pixels": list(expected_size),
            "image_dimensions_passed": dimensions_pass,
            "build_audit_vector_gate_passed": vector_gate,
            "manifest_status_before_gate": manifest.get("status"),
            "retained_input_fingerprints": _artifact_fingerprints(fingerprint_paths),
        },
        "vector_integrity": {
            "scope_note": "A passing structure audit does not establish visual fidelity.",
            "checks": vector_checks,
            "passed": vector_gate,
        },
        "field_geometry": field,
        "plaque_geometry": plaque,
        "trellis_geometry": pattern,
        "blockers": blockers,
        "phase_gate_advanced": passed,
        "next_action": (
            "Advance to Arabic tracing only from this retained workspace."
            if passed
            else "Correct the failing Phase 2 geometry and retain a new run before Arabic tracing."
        ),
    }
