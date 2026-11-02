"""Validate retained Phase 2 vector-integrity and raster-geometry evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from corel_operator.phase2_validation import (  # noqa: E402
    Phase2ValidationError,
    validate_phase2_workspace,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Defaults to <workspace>/phase2_geometry_validation.json.",
    )
    args = parser.parse_args()
    try:
        report = validate_phase2_workspace(args.workspace)
    except Phase2ValidationError as exc:
        parser.error(str(exc))
    output = args.output or args.workspace / "phase2_geometry_validation.json"
    output = output.expanduser().resolve()
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "result": report["result"],
                "report": str(output),
                "blockers": report["blockers"],
                "field_max_error_mm": report["field_geometry"]["maximum_edge_error_mm"],
                "plaque_iou": report["plaque_geometry"]["iou"],
                "trellis_f1": report["trellis_geometry"]["tolerant_f1"],
            },
            indent=2,
        )
    )
    return 0 if report["result"] == "PASS_PHASE2_GATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
