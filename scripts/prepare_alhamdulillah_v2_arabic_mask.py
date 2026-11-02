"""Prepare a reproducible, analysis-only Arabic silhouette for V2 Phase 3."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corel_operator.calligraphy_tracing import (  # noqa: E402
    connected_components,
    extract_warm_calligraphy_mask,
    rasterize_pen_commands,
)
from scripts.build_alhamdulillah_v2_structure import (  # noqa: E402
    _field_pixels,
    _plaque_commands,
)


REGION = (230, 115, 1035, 624)
MINIMUM_CHANNEL_TOTAL = 350
MINIMUM_RED_BLUE_DIFFERENCE = 40
NEUTRAL_BRIGHT_TOTAL = 660
CLOSING_SIZE = 5
TRACE_MINIMUM_COMPONENT_AREA = 100


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _component_record(component: Any) -> dict[str, Any]:
    return {
        "label": component.label,
        "pixels": component.area,
        "bbox_pixels": list(component.bbox),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--run-name", default="phase3_mask_extraction01")
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    run_dir = workspace / args.run_name
    gate_path = workspace / "phase2_geometry_validation.json"
    measurements_path = workspace / "v2_measurements.json"
    reference_path = workspace / "00_reference_nonprinting" / "reference_rectified_a4.png"
    raw_path = run_dir / "phase3_arabic_mask_raw_analysis.png"
    plaque_roi_path = run_dir / "phase3_arabic_plaque_roi_analysis.png"
    clean_path = run_dir / "phase3_arabic_silhouette_extracted.png"
    audit_path = run_dir / "phase3_arabic_mask_extraction_audit.json"
    for path in (gate_path, measurements_path, reference_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required retained Phase 2 input is missing: {path}")
    if run_dir.exists():
        raise FileExistsError(f"Refusing to reuse Arabic extraction run directory: {run_dir}")

    gate = _load_json(gate_path)
    if gate.get("result") != "PASS_PHASE2_GATE":
        raise ValueError("Arabic mask extraction requires PASS_PHASE2_GATE.")
    if not gate.get("validation_scope", {}).get("arabic_tracing_authorized"):
        raise ValueError("The passing report does not authorize Arabic tracing.")
    expected_hash = gate["artifact_integrity"]["retained_input_fingerprints"]["reference"]["sha256"]
    actual_hash = _sha256(reference_path)
    if actual_hash != expected_hash:
        raise ValueError("Rectified reference bytes do not match the passing Phase 2 report.")

    run_dir.mkdir(parents=False, exist_ok=False)
    reference = Image.open(reference_path).convert("RGB")
    raw_unclipped, clean_unclipped = extract_warm_calligraphy_mask(
        reference,
        region=REGION,
        minimum_channel_total=MINIMUM_CHANNEL_TOTAL,
        minimum_red_blue_difference=MINIMUM_RED_BLUE_DIFFERENCE,
        neutral_bright_total=NEUTRAL_BRIGHT_TOTAL,
        closing_size=CLOSING_SIZE,
    )
    measurements = _load_json(measurements_path)
    plaque_roi = rasterize_pen_commands(
        reference.size,
        _plaque_commands(_field_pixels(measurements)),
    )
    raw = ImageChops.multiply(raw_unclipped, plaque_roi)
    clean = ImageChops.multiply(clean_unclipped, plaque_roi)
    raw.save(raw_path)
    plaque_roi.save(plaque_roi_path)
    clean.save(clean_path)
    all_components = connected_components(clean)
    retained_components = connected_components(
        clean,
        minimum_area=TRACE_MINIMUM_COMPONENT_AREA,
    )
    retained_pixels = sum(component.area for component in retained_components)
    audit = {
        "schema_version": "alhamdulillah-phase3-mask-extraction-v1",
        "result": "READY_FOR_TRACE_MANUAL_REVIEW_REQUIRED",
        "scope": "Analysis-only color segmentation; this bitmap must never be imported on a printable layer.",
        "source": {
            "path": str(reference_path),
            "sha256": actual_hash,
            "dimensions_pixels": list(reference.size),
            "bound_to_phase2_gate": str(gate_path),
        },
        "extraction": {
            "region_pixels": list(REGION),
            "classification": (
                "(red + green + blue > 350 and red - blue > 40) "
                "or red + green + blue > 660"
            ),
            "morphological_closing_size_pixels": CLOSING_SIZE,
            "unclipped_clean_foreground_pixels": clean_unclipped.histogram()[255],
            "restricted_to_passing_plaque_geometry": True,
            "raw_foreground_pixels": raw.histogram()[255],
            "clean_foreground_pixels": clean.histogram()[255],
            "trace_minimum_component_area_pixels": TRACE_MINIMUM_COMPONENT_AREA,
            "retained_foreground_pixels": retained_pixels,
        },
        "components": {
            "all_count": len(all_components),
            "retained_count": len(retained_components),
            "retained": [_component_record(item) for item in retained_components],
        },
        "manual_review": {
            "required": True,
            "completed": False,
            "checks": [
                "Reject trellis fragments at the extraction-region boundary.",
                "Confirm detached components are Arabic marks rather than photographic glare.",
                "Confirm major negative spaces and stroke terminals against the rectified source.",
            ],
        },
        "artifacts": {
            "raw_mask_analysis_only": str(raw_path),
            "plaque_roi_analysis_only": str(plaque_roi_path),
            "clean_silhouette_analysis_only": str(clean_path),
        },
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "result": audit["result"],
        "run_directory": str(run_dir),
        "clean_mask": str(clean_path),
        "foreground_pixels": clean.histogram()[255],
        "retained_components": len(retained_components),
        "retained_pixels": retained_pixels,
        "manual_review_required": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
