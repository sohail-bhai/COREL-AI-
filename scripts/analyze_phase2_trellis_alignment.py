"""Measure local trellis displacement between a Phase 2 preview and reference."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corel_operator.phase2_validation import (  # noqa: E402
    _count_mask,
    _field_metrics,
    _load_json,
    _pattern_metrics,
    _plaque_metrics,
)


def _tile_mask(
    size: tuple[int, int],
    region: Image.Image,
    box: tuple[int, int, int, int],
) -> Image.Image:
    tile = Image.new("L", size, 0)
    ImageDraw.Draw(tile).rectangle(box, fill=255)
    return ImageChops.multiply(tile, region)


def _shifted_crop(
    mask: Image.Image,
    box: tuple[int, int, int, int],
    dx: int,
    dy: int,
) -> Image.Image:
    left, top, right, bottom = box
    return mask.crop((left - dx, top - dy, right - dx, bottom - dy))


def _best_translation(
    reference_edges: Image.Image,
    preview_edges: Image.Image,
    region: Image.Image,
    box: tuple[int, int, int, int],
    tolerance: int,
    search: int,
) -> dict[str, Any]:
    local_region = region.crop(box)
    reference = ImageChops.multiply(reference_edges.crop(box), local_region)
    reference_count = _count_mask(reference)
    expanded_reference = reference.filter(ImageFilter.MaxFilter(tolerance * 2 + 1))
    candidates: list[tuple[float, float, float, int, int, int]] = []
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            preview = ImageChops.multiply(
                _shifted_crop(preview_edges, box, dx, dy), local_region
            )
            preview_count = _count_mask(preview)
            if not preview_count or not reference_count:
                continue
            matched_preview = _count_mask(
                ImageChops.multiply(preview, expanded_reference)
            )
            expanded_preview = preview.filter(
                ImageFilter.MaxFilter(tolerance * 2 + 1)
            )
            matched_reference = _count_mask(
                ImageChops.multiply(reference, expanded_preview)
            )
            precision = matched_preview / preview_count
            recall = matched_reference / reference_count
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision + recall
                else 0.0
            )
            candidates.append((f1, precision, recall, dx, dy, preview_count))
    if not candidates:
        return {"evaluated": False, "box": list(box)}
    f1, precision, recall, dx, dy, preview_count = max(candidates)
    return {
        "evaluated": True,
        "box": list(box),
        "best_preview_translation_pixels": {"x": dx, "y": dy},
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "preview_edge_pixels": preview_count,
        "reference_edge_pixels": reference_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--search-pixels", type=int, default=16)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    measurements = _load_json(workspace / "v2_measurements.json")
    reference = Image.open(
        workspace / "00_reference_nonprinting" / "reference_rectified_a4.png"
    ).convert("RGB")
    preview = Image.open(workspace / "phase2_structure_preview.png").convert("RGB")
    field_metrics, field = _field_metrics(measurements, preview)
    plaque_metrics, plaque = _plaque_metrics(reference, preview, field)
    pattern_metrics, diagnostics = _pattern_metrics(reference, preview, field, plaque)
    region, reference_edges, preview_edges = diagnostics
    left, top, right, bottom = field
    width = right - left
    height = bottom - top
    quarter = width // 4
    boxes = {
        "upper_left": (left, top, left + quarter, top + height // 3),
        "upper_right": (right - quarter, top, right, top + height // 3),
        "lower_left": (left, top + height * 4 // 5, left + quarter, bottom),
        "lower_center_left": (
            left + quarter,
            top + height * 4 // 5,
            left + quarter * 2,
            bottom,
        ),
        "lower_center_right": (
            left + quarter * 2,
            top + height * 4 // 5,
            left + quarter * 3,
            bottom,
        ),
        "lower_right": (right - quarter, top + height * 4 // 5, right, bottom),
    }
    local = {
        name: _best_translation(
            reference_edges,
            preview_edges,
            _tile_mask(preview.size, region, box),
            box,
            int(pattern_metrics["tolerance_pixels"]),
            args.search_pixels,
        )
        for name, box in boxes.items()
    }
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "field_passed": field_metrics["passed"],
                "plaque_passed": plaque_metrics["passed"],
                "global_trellis": pattern_metrics,
                "local_alignment": local,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
