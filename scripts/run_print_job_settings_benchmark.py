"""Audit the poster PDF and exercise print-job planning/execution in CorelDRAW X7."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom
from PIL import Image, ImageDraw, ImageFont

from corel_operator.corel_bridge import CorelBridge
from corel_operator.print_jobs import inspect_raster_artwork, plan_print_job


SPEC_PATH = ROOT / "benchmarks" / "print_job_settings.json"
OUTPUT_ROOT = ROOT / "output"


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    file_name = "arialbd.ttf" if bold else "arial.ttf"
    try:
        return ImageFont.truetype(str(Path("C:/Windows/Fonts") / file_name), size)
    except OSError:
        return ImageFont.load_default()


def create_cmyk_fixture(path: Path) -> None:
    """Create 3.75 x 2.25 inch bleed-inclusive CMYK artwork at 300 DPI."""
    image = Image.new("CMYK", (1125, 675), (95, 75, 20, 65))
    draw = ImageDraw.Draw(image)
    coral = (0, 72, 55, 0)
    aqua = (62, 0, 35, 0)
    cream = (3, 3, 9, 0)
    navy = (95, 75, 20, 65)

    draw.rectangle((0, 0, 1124, 48), fill=coral)
    draw.rectangle((0, 627, 1124, 674), fill=aqua)
    draw.ellipse((55, 100, 410, 455), fill=aqua)
    draw.ellipse((105, 150, 360, 405), fill=navy)
    draw.ellipse((165, 210, 300, 345), fill=coral)
    draw.rectangle((445, 140, 1045, 150), fill=coral)
    draw.text((445, 175), "PRESS SYSTEM / 01", font=_font(42, bold=True), fill=cream)
    draw.text((445, 245), "CMYK PRINT FIXTURE", font=_font(48, bold=True), fill=aqua)
    draw.text((445, 330), "TRIM 3.5 x 2.0 IN", font=_font(27, bold=True), fill=cream)
    draw.text((445, 380), "BLEED 0.125 / SAFE 0.125", font=_font(25), fill=cream)
    draw.text((445, 455), "300 DPI / MIXED ROTATION TEST", font=_font(22), fill=coral)
    draw.rectangle((445, 510, 1045, 520), fill=aqua)
    image.save(path, format="TIFF", compression="tiff_lzw", dpi=(300, 300))


def _pdf_box(data: bytes, name: str) -> dict[str, float] | None:
    match = re.search(
        rb"/" + name.encode("ascii") + rb"\s*\[\s*([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s*\]",
        data,
    )
    if not match:
        return None
    x1, y1, x2, y2 = (float(value) for value in match.groups())
    return {
        "x1_points": x1,
        "y1_points": y1,
        "x2_points": x2,
        "y2_points": y2,
        "width_inches": round((x2 - x1) / 72.0, 4),
        "height_inches": round((y2 - y1) / 72.0, 4),
    }


def inspect_pdf_tokens(path: Path) -> dict[str, Any]:
    """Perform a bounded token-level PDF audit; this is not a full PDF/X validator."""
    data = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(data),
        "media_box": _pdf_box(data, "MediaBox"),
        "trim_box": _pdf_box(data, "TrimBox"),
        "bleed_box": _pdf_box(data, "BleedBox"),
        "output_intent_tokens": data.count(b"/OutputIntent"),
        "device_rgb_tokens": data.count(b"/DeviceRGB"),
        "device_cmyk_tokens": data.count(b"/DeviceCMYK"),
        "font_file_tokens": data.count(b"/FontFile"),
    }


def _latest_poster_pdf() -> Path:
    candidates = list(OUTPUT_ROOT.glob("future_forms_benchmark_*/future_forms_2026.pdf"))
    if not candidates:
        raise FileNotFoundError("No Future Forms benchmark PDF was found beneath output/.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _job_arguments(copies: int) -> dict[str, Any]:
    return {
        "finished_width_inches": 3.5,
        "finished_height_inches": 2.0,
        "sheet_width_inches": 12.0,
        "sheet_height_inches": 18.0,
        "copies": copies,
        "bleed_inches": 0.125,
        "safe_margin_inches": 0.125,
        "margin_inches": 0.25,
        "gutter_inches": 0.125,
        "minimum_dpi": 300.0,
        "artwork_includes_bleed": True,
        "fit_mode": "contain",
        "allow_low_resolution": False,
        "rotation_policy": "best_fit",
        "sheet_orientation": "fixed",
        "gripper_inches": 0.375,
        "gripper_edge": "bottom",
        "mark_clearance_inches": 0.125,
    }


def _close_enough(actual: Any, expected: float, tolerance: float = 0.01) -> bool:
    try:
        return abs(float(actual) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poster-pdf", type=Path, default=None)
    args = parser.parse_args()

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    poster_pdf = (args.poster_pdf or _latest_poster_pdf()).expanduser().resolve()
    if not poster_pdf.is_file():
        raise FileNotFoundError(f"Poster PDF does not exist: {poster_pdf}")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"print_settings_benchmark_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    fixture_path = run_dir / "cmyk_bleed_fixture_300dpi.tif"
    cdr_path = run_dir / "imposed_12x18.cdr"
    pdf_path = run_dir / "imposed_12x18.pdf"
    result_path = run_dir / "benchmark_result.json"

    trace: list[dict[str, Any]] = []
    bridge = CorelBridge()
    document = None

    def call(operation: str, fn: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        try:
            value = fn()
        except Exception as exc:
            trace.append({
                "operation": operation,
                "status": "FAIL",
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": f"{type(exc).__name__}: {exc}",
            })
            raise
        trace.append({
            "operation": operation,
            "status": "PASS",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        })
        return value

    pythoncom.CoInitialize()
    try:
        call("create_cmyk_fixture", lambda: create_cmyk_fixture(fixture_path))
        poster_audit = call("inspect_poster_pdf", lambda: inspect_pdf_tokens(poster_pdf))
        artwork = call("inspect_raster_artwork", lambda: inspect_raster_artwork(str(fixture_path)))

        quantity_plan = call(
            "plan_print_job_quantity",
            lambda: plan_print_job(str(fixture_path), **_job_arguments(250)),
        )
        sheet_plan = call(
            "plan_print_job_sheet",
            lambda: plan_print_job(str(fixture_path), **_job_arguments(19)),
        )

        status = call("corel_status", bridge.connect)
        prepared = call(
            "prepare_print_job",
            lambda: bridge.prepare_print_job(
                str(fixture_path),
                object_name_prefix="PressCard",
                **_job_arguments(19),
            ),
        )
        document = bridge.target_doc
        page = call("get_page_bounds", lambda: bridge.get_page_bounds(1))
        objects = call("list_objects", lambda: bridge.list_objects(100))
        call("save_document", lambda: bridge.save_document(str(cdr_path)))
        call("export_pdf", lambda: bridge.export_pdf(str(pdf_path)))
        imposed_pdf_audit = call("inspect_imposed_pdf", lambda: inspect_pdf_tokens(pdf_path))

        media = poster_audit["media_box"] or {}
        poster_checks = {
            "trim_dimensions": _close_enough(media.get("width_inches"), 8.27)
            and _close_enough(media.get("height_inches"), 11.69),
            "trim_box_present": poster_audit["trim_box"] is not None,
            "bleed_box_present": poster_audit["bleed_box"] is not None,
            "cmyk_or_managed_output": (
                poster_audit["device_cmyk_tokens"] > 0
                or poster_audit["output_intent_tokens"] > 0
            ),
            "output_intent_present": poster_audit["output_intent_tokens"] > 0,
            "embedded_font_evidence": poster_audit["font_file_tokens"] > 0,
        }
        poster_score = sum(5 for passed in poster_checks.values() if passed)

        quantity_block_codes = {
            item.get("code") for item in quantity_plan["preflight"]["blocking_issues"]
        }
        preflight_checks = {
            item["check"]: item for item in sheet_plan["preflight"]["checks"]
        }
        layout = sheet_plan["layout"]
        margins = layout["margins_inches"]
        output_media = imposed_pdf_audit["media_box"] or {}
        live_checks = {
            "fixture_metadata": (
                artwork["mode"] == "CMYK"
                and artwork["color_space"] == "cmyk"
                and artwork["width_pixels"] == 1125
                and artwork["height_pixels"] == 675
            ),
            "fixture_dpi": (
                _close_enough(artwork["metadata_dpi"]["x"], 300)
                and _close_enough(artwork["metadata_dpi"]["y"], 300)
            ),
            "trim_bleed_safe_geometry": (
                sheet_plan["job"]["placed_size_inches"] == {"width": 3.75, "height": 2.25}
                and sorted([
                    round(float(sheet_plan["placements"][0]["safe_box"]["width_inches"]), 2),
                    round(float(sheet_plan["placements"][0]["safe_box"]["height_inches"]), 2),
                ]) == [1.75, 3.25]
            ),
            "effective_margins": all(
                _close_enough(margins[edge], expected)
                for edge, expected in {"left": 0.375, "top": 0.375, "right": 0.375, "bottom": 0.75}.items()
            ),
            "optimized_layout": (
                layout["layout_strategy"] == "mixed_rotated_columns"
                and layout["capacity"] == 19
                and layout["mixed_rotation"] is True
            ),
            "production_quantity_math": (
                quantity_plan["copies_per_sheet"] == 19
                and quantity_plan["sheets_required"] == 14
                and quantity_plan["total_produced"] == 266
                and quantity_plan["overage"] == 16
                and quantity_plan["ready_for_execution"] is False
                and "COPY_COUNT_EXCEEDS_SHEET" in quantity_block_codes
            ),
            "effective_resolution": (
                sheet_plan["effective_dpi"]["minimum"] >= 300
                and preflight_checks["effective_resolution"]["status"] == "passed"
            ),
            "bleed_confirmation": preflight_checks["bleed_content"]["status"] == "passed",
            "limitations_reported": (
                preflight_checks["icc_profile"]["status"] == "warning"
                and preflight_checks["print_marks"]["status"] == "not_checked"
                and preflight_checks["output_profile"]["status"] == "not_checked"
                and preflight_checks["pdf_export"]["status"] == "not_checked"
            ),
            "sheet_plan_executable": sheet_plan["ready_for_execution"] is True,
            "live_placement_verified": (
                prepared["created_count"] == 19
                and prepared["post_execution_verification"] is True
                and not prepared["discrepancies"]
                and prepared["print_ready"] is False
            ),
            "document_readback": (
                _close_enough(page["bounds"]["width"], 12.0)
                and _close_enough(page["bounds"]["height"], 18.0)
                and objects["total_on_page"] == 19
            ),
            "artifacts_nonempty": cdr_path.stat().st_size > 0 and pdf_path.stat().st_size > 0,
            "exported_pdf_sheet_size": (
                _close_enough(output_media.get("width_inches"), 12.0)
                and _close_enough(output_media.get("height_inches"), 18.0)
            ),
        }
        live_score = sum(5 for passed in live_checks.values() if passed)
        workflow_passed = live_score == 70
        poster_press_ready = all(poster_checks.values())
        if workflow_passed and poster_press_ready:
            verdict = "PASS_PRESS_READY"
        elif workflow_passed:
            verdict = "CONDITIONAL_POSTER_NOT_PRESS_READY"
        else:
            verdict = "FAIL_WORKFLOW"

        result = {
            "benchmark_id": spec["benchmark_id"],
            "run_id": run_id,
            "verdict": verdict,
            "poster_pdf": {
                "audit": poster_audit,
                "checks": poster_checks,
                "score": poster_score,
                "maximum_score": 30,
                "press_ready": poster_press_ready,
            },
            "live_job": {
                "corel_version": status.get("version"),
                "artwork": artwork,
                "quantity_plan": {
                    "ready_for_execution": quantity_plan["ready_for_execution"],
                    "copies_per_sheet": quantity_plan["copies_per_sheet"],
                    "sheets_required": quantity_plan["sheets_required"],
                    "total_produced": quantity_plan["total_produced"],
                    "overage": quantity_plan["overage"],
                    "blocking_issue_codes": sorted(code for code in quantity_block_codes if code),
                },
                "sheet_plan": {
                    "ready_for_execution": sheet_plan["ready_for_execution"],
                    "layout": layout,
                    "effective_dpi": sheet_plan["effective_dpi"],
                    "preflight_status": sheet_plan["preflight"]["status"],
                    "warnings": sheet_plan["preflight"]["warnings"],
                },
                "prepared": {
                    "created_count": prepared["created_count"],
                    "post_execution_verification": prepared["post_execution_verification"],
                    "discrepancies": prepared["discrepancies"],
                    "print_ready": prepared["print_ready"],
                },
                "checks": live_checks,
                "score": live_score,
                "maximum_score": 70,
            },
            "scores": {
                "poster_pdf_audit": poster_score,
                "live_workflow": live_score,
                "total": poster_score + live_score,
                "maximum": 100,
            },
            "imposed_pdf_audit": imposed_pdf_audit,
            "artifacts": {
                "fixture": str(fixture_path),
                "cdr": str(cdr_path),
                "pdf": str(pdf_path),
                "result_json": str(result_path),
            },
            "tool_trace": trace,
            "limitations": spec["expected_limitations"],
        }
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print(f"Verdict: {verdict}")
        print(f"Poster PDF audit: {poster_score}/30")
        print(f"Live print workflow: {live_score}/70")
        print(f"Combined score: {poster_score + live_score}/100")
        print(f"Layout: {layout['layout_strategy']} / {layout['capacity']} per sheet")
        print("Quantity: 250 requested / 14 sheets / 266 produced / 16 overage")
        print(f"CDR: {cdr_path} ({cdr_path.stat().st_size:,} bytes)")
        print(f"PDF: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
        print(f"Result: {result_path}")
        return 0 if workflow_passed else 1
    except Exception as exc:
        failure = {
            "benchmark_id": spec["benchmark_id"],
            "run_id": run_id,
            "verdict": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "tool_trace": trace,
        }
        result_path.write_text(json.dumps(failure, indent=2), encoding="utf-8")
        print(f"Benchmark failed: {failure['error']}")
        print(f"Failure trace: {result_path}")
        return 1
    finally:
        if document is not None:
            try:
                document.Close()
            except Exception:
                pass
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
