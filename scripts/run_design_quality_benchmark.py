"""Run the fixed Future Forms poster benchmark against live CorelDRAW X7."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom

from corel_operator.corel_bridge import CorelBridge
from corel_operator.design_plans import preview_design_plan, validate_design_plan


SPEC_PATH = ROOT / "benchmarks" / "future_forms_poster.json"
OUTPUT_ROOT = ROOT / "output"

NAVY = (11, 16, 38)
CREAM = (244, 241, 232)
CORAL = (255, 90, 95)
AQUA = (85, 230, 193)


def _fill(rgb: tuple[int, int, int]) -> dict[str, int]:
    return {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}


def _rect(
    element_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    color: tuple[int, int, int],
) -> dict[str, Any]:
    return {
        "id": element_id,
        "type": "rectangle",
        "x_inches": x,
        "y_inches": y,
        "width_inches": width,
        "height_inches": height,
        "fill": _fill(color),
        # Explicit RGB works around preview_design_plan reading schema-defaulted
        # outline colors before jsonschema has materialized those defaults.
        "outline": {"width_points": 0, "red": 0, "green": 0, "blue": 0},
    }


def _ellipse(
    element_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    color: tuple[int, int, int],
) -> dict[str, Any]:
    item = _rect(element_id, x, y, width, height, color)
    item["type"] = "ellipse"
    return item


def _text(
    element_id: str,
    value: str,
    x: float,
    y: float,
    size: float,
    color: tuple[int, int, int],
    *,
    bold: bool = False,
) -> dict[str, Any]:
    return {
        "id": element_id,
        "type": "text",
        "x_inches": x,
        "y_inches": y,
        "text": value,
        "font": "Arial",
        "font_size_points": size,
        "bold": bold,
        "fill": _fill(color),
        "outline": {"width_points": 0, "red": 0, "green": 0, "blue": 0},
    }


def build_plan() -> dict[str, Any]:
    elements: list[dict[str, Any]] = [
        _rect("background", 0, 0, 8.27, 11.69, NAVY),
        _rect("frame_outer", 0.30, 0.30, 7.67, 11.09, CREAM),
        _rect("frame_inner", 0.325, 0.325, 7.62, 11.04, NAVY),
        _rect("right_rail", 7.74, 0.325, 0.205, 11.04, CORAL),
        _text("header_kicker", "GLOBAL CREATIVE SUMMIT", 0.62, 10.91, 10, AQUA, bold=True),
        _text("header_meta", "BERLIN / 18-20 SEP", 5.88, 10.91, 9, CREAM, bold=True),
        _rect("header_rule", 0.62, 10.64, 6.89, 0.025, AQUA),
        _rect("edition_pill", 0.62, 10.18, 1.48, 0.32, CORAL),
        _text("edition_pill_text", "NEW MODERNISM", 0.74, 10.28, 8, NAVY, bold=True),
        _rect("micro_bar", 6.18, 10.20, 0.30, 0.025, AQUA),
        _text("title_future", "FUTURE", 0.60, 9.53, 58, CREAM, bold=True),
        _text("title_forms", "FORMS", 0.56, 8.42, 82, CORAL, bold=True),
        _text("title_subtitle", "DESIGNING WHAT'S NEXT", 0.65, 7.78, 13, AQUA, bold=True),
        _rect("accent_square", 0.62, 7.39, 0.12, 0.12, CORAL),
        _ellipse("year_outer", 5.83, 8.20, 1.48, 1.48, AQUA),
        _ellipse("year_inner", 6.04, 8.41, 1.06, 1.06, NAVY),
        _text("year_text", "26", 6.18, 8.69, 36, CREAM, bold=True),
        _text("year_caption", "EDITION", 6.22, 8.47, 7.5, AQUA, bold=True),
        _ellipse("orbit_outer_aqua", 3.25, 2.95, 4.55, 4.55, AQUA),
        _ellipse("orbit_outer_cut", 3.30, 3.00, 4.45, 4.45, NAVY),
        _ellipse("orbit_mid_coral", 3.60, 3.30, 3.85, 3.85, CORAL),
        _ellipse("orbit_mid_cut", 3.66, 3.36, 3.73, 3.73, NAVY),
        _ellipse("orbit_disc_coral", 4.10, 3.80, 2.85, 2.85, CORAL),
        _ellipse("orbit_disc_cut", 4.47, 4.17, 2.11, 2.11, NAVY),
        _ellipse("orbit_disc_aqua", 4.83, 4.53, 1.39, 1.39, AQUA),
        _ellipse("orbit_core_cut", 5.10, 4.80, 0.85, 0.85, NAVY),
        _ellipse("orbit_core_cream", 5.34, 5.04, 0.37, 0.37, CREAM),
        _rect("orbit_bar_cream", 2.90, 5.42, 4.87, 0.065, CREAM),
        _rect("orbit_bar_navy", 3.45, 4.78, 4.10, 0.045, NAVY),
        _rect("orbit_bar_coral", 3.02, 6.14, 1.18, 0.075, CORAL),
        _text("orbit_label", "ORBIT / 01", 3.02, 6.34, 8, CREAM, bold=True),
        _text("orbit_coordinates", "X 05.525 / Y 05.225", 3.02, 3.08, 7, AQUA),
        _rect("info_panel_outer", 0.62, 1.36, 3.13, 1.47, CREAM),
        _rect("info_panel_inner", 0.65, 1.39, 3.07, 1.41, NAVY),
        _text("date_text", "18-20 SEPTEMBER", 0.84, 2.40, 14, CORAL, bold=True),
        _text("discipline_text", "TYPOGRAPHY / MOTION / AI", 0.84, 2.00, 8.5, CREAM, bold=True),
        _text("theme_text", "IDEAS / SYSTEMS / CULTURE", 0.84, 1.68, 8.5, AQUA),
        _text("venue_text", "HKW BERLIN", 4.45, 2.40, 18, CREAM, bold=True),
        _text("program_text", "WORKSHOPS + TALKS + EXHIBITIONS", 4.55, 2.00, 7.5, AQUA, bold=True),
        _text("url_text", "FUTUREFORMS.EXAMPLE", 4.55, 1.68, 8.5, CREAM),
        _rect("footer_rule", 0.60, 0.88, 7.07, 0.025, CORAL),
        _text("footer_message_draft", "BUILD THE FUTURE.", 5.67, 0.57, 8, CREAM, bold=True),
    ]

    dot_colors = (AQUA, CORAL, CREAM)
    for row in range(4):
        for column in range(4):
            elements.append(
                _ellipse(
                    f"matrix_dot_{row + 1}_{column + 1}",
                    0.76 + column * 0.31,
                    3.90 + row * 0.31,
                    0.09,
                    0.09,
                    dot_colors[(row + column) % len(dot_colors)],
                )
            )

    return {
        "version": "1.0",
        "name": "Future Forms 2026 Poster",
        "description": "Original vector-only benchmark poster for tool-use and visual-quality evaluation.",
        "canvas": {"width_inches": 8.27, "height_inches": 11.69, "unit": "inch"},
        "elements": elements,
        "validations": {
            "expected_element_count": len(elements),
            "bounding_box_within_canvas": True,
        },
    }


def _rgb_from_info(info: dict[str, Any]) -> list[int] | None:
    try:
        value = info["object"]["fill"]["color"]["value"]
        return [int(value["red"]), int(value["green"]), int(value["blue"])]
    except (KeyError, TypeError, ValueError):
        return None


def main() -> int:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    plan = build_plan()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"future_forms_benchmark_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    cdr_path = run_dir / "future_forms_2026.cdr"
    pdf_path = run_dir / "future_forms_2026.pdf"
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
        status = call("corel_status", bridge.connect)
        created = call("create_document", lambda: bridge.create_document(8.27, 11.69))
        call("use_active_document", lambda: bridge.use_active_document(confirm_existing_document=True))
        document = bridge.target_doc

        validation = call("validate_design_plan", lambda: validate_design_plan(plan))
        preview = call("preview_design_plan", lambda: preview_design_plan(plan))
        execution = call(
            "execute_design_plan",
            lambda: bridge.execute_design_plan(plan, rollback_on_failure=True),
        )

        ring_names = [
            "orbit_outer_aqua", "orbit_outer_cut", "orbit_mid_coral", "orbit_mid_cut",
            "orbit_disc_coral", "orbit_disc_cut", "orbit_disc_aqua", "orbit_core_cut",
            "orbit_core_cream",
        ]
        call(
            "align_objects",
            lambda: bridge.align_objects(
                ring_names, horizontal="center", vertical="center", align_to="last_selected"
            ),
        )

        call("move_object", lambda: bridge.move_object(4.55, 2.40, object_name="venue_text"))
        call(
            "resize_object",
            lambda: bridge.resize_object(
                0.10, 0.10, keep_aspect_ratio=True, object_name="accent_square"
            ),
        )
        call(
            "set_text_content",
            lambda: bridge.set_text_content(
                "BUILD THE UNEXPECTED.", object_name="footer_message_draft"
            ),
        )
        call(
            "rename_object",
            lambda: bridge.rename_object(
                "footer_message", object_name="footer_message_draft"
            ),
        )

        call(
            "draw_ellipse",
            lambda: bridge.draw_ellipse(6.54, 10.16, 0.09, 0.09, "signal_dot_01"),
        )
        call(
            "set_fill_color",
            lambda: bridge.set_fill_color(*CORAL, object_name="signal_dot_01"),
        )
        call(
            "set_outline",
            lambda: bridge.set_outline(*NAVY, width_points=0, object_name="signal_dot_01"),
        )
        for index, offset in enumerate((0.22, 0.44, 0.66), start=2):
            call(
                "duplicate_object",
                lambda index=index, offset=offset: bridge.duplicate_object(
                    offset, 0, object_name="signal_dot_01", new_name=f"signal_dot_{index:02d}"
                ),
            )

        call(
            "draw_rectangle",
            lambda: bridge.draw_rectangle(0.62, 0.55, 0.30, 0.03, "footer_accent"),
        )
        call(
            "set_fill_color",
            lambda: bridge.set_fill_color(*AQUA, object_name="footer_accent"),
        )
        call(
            "set_outline",
            lambda: bridge.set_outline(*NAVY, width_points=0, object_name="footer_accent"),
        )
        call(
            "add_text",
            lambda: bridge.add_text(
                "FF / 026", 1.06, 0.57, size_pt=8, font="Arial", bold=True,
                object_name="footer_index"
            ),
        )
        call(
            "set_fill_color",
            lambda: bridge.set_fill_color(*CREAM, object_name="footer_index"),
        )
        call(
            "set_outline",
            lambda: bridge.set_outline(*NAVY, width_points=0, object_name="footer_index"),
        )

        call(
            "align_to_page",
            lambda: bridge.align_to_page(
                ["footer_rule"], horizontal="center", align_as_group=True
            ),
        )

        orbit_group_names = ring_names + [
            "orbit_bar_cream", "orbit_bar_navy", "orbit_bar_coral",
        ]
        dot_names = [f"matrix_dot_{row}_{column}" for row in range(1, 5) for column in range(1, 5)]
        signal_names = [f"signal_dot_{index:02d}" for index in range(1, 5)]
        call(
            "group_shapes",
            lambda: bridge.group_shapes(orbit_group_names, "Orbit_System_Group"),
        )
        call(
            "group_shapes",
            lambda: bridge.group_shapes(dot_names, "Dot_Matrix_Group"),
        )
        call(
            "group_shapes",
            lambda: bridge.group_shapes(signal_names, "Signal_Dots_Group"),
        )
        call(
            "group_shapes",
            lambda: bridge.group_shapes(["year_outer", "year_inner"], "Year_Rings_Group"),
        )
        call(
            "group_shapes",
            lambda: bridge.group_shapes(
                ["info_panel_outer", "info_panel_inner"], "Info_Panel_Frame_Group"
            ),
        )

        page = call("get_page_bounds", lambda: bridge.get_page_bounds(1))
        objects = call("list_objects", lambda: bridge.list_objects(200))

        required_text_objects = {
            "header_kicker": "GLOBAL CREATIVE SUMMIT",
            "header_meta": "BERLIN / 18-20 SEP",
            "title_future": "FUTURE",
            "title_forms": "FORMS",
            "title_subtitle": "DESIGNING WHAT'S NEXT",
            "year_text": "26",
            "year_caption": "EDITION",
            "date_text": "18-20 SEPTEMBER",
            "discipline_text": "TYPOGRAPHY / MOTION / AI",
            "theme_text": "IDEAS / SYSTEMS / CULTURE",
            "venue_text": "HKW BERLIN",
            "program_text": "WORKSHOPS + TALKS + EXHIBITIONS",
            "url_text": "FUTUREFORMS.EXAMPLE",
            "footer_index": "FF / 026",
            "footer_message": "BUILD THE UNEXPECTED.",
        }
        text_readback: dict[str, str | None] = {}
        for object_name in required_text_objects:
            info = call(
                "get_object_info",
                lambda object_name=object_name: bridge.get_object_info(object_name=object_name),
            )
            text_readback[object_name] = (info["object"].get("text") or {}).get("text")

        color_samples: dict[str, list[int] | None] = {}
        for object_name in ("background", "title_future", "title_forms", "title_subtitle"):
            info = call(
                "get_object_info",
                lambda object_name=object_name: bridge.get_object_info(object_name=object_name),
            )
            color_samples[object_name] = _rgb_from_info(info)

        call("save_document", lambda: bridge.save_document(str(cdr_path)))
        call("export_pdf", lambda: bridge.export_pdf(str(pdf_path)))

        expected_groups = set(spec["constraints"]["required_named_groups"])
        actual_names = {item["object_name"] for item in objects["objects"]}
        expected_text = required_text_objects
        text_matches = {
            name: text_readback.get(name) == value for name, value in expected_text.items()
        }
        expected_colors = {
            "background": list(NAVY),
            "title_future": list(CREAM),
            "title_forms": list(CORAL),
            "title_subtitle": list(AQUA),
        }
        color_matches = {
            name: color_samples.get(name) == value for name, value in expected_colors.items()
        }
        bounds = page["bounds"]
        page_matches = (
            abs(float(bounds["width"]) - 8.27) <= 0.01
            and abs(float(bounds["height"]) - 11.69) <= 0.01
        )
        failed_operations = [item for item in trace if item["status"] != "PASS"]
        distinct_operations = sorted({item["operation"] for item in trace})
        artifacts_ok = cdr_path.stat().st_size > 0 and pdf_path.stat().st_size > 0

        checks = {
            "connected": bool(status.get("connected")),
            "page_size_matches": page_matches,
            "plan_validation_ready": bool(validation.get("ready_for_execution")),
            "plan_preview_ready": bool(preview.get("ready_for_execution")),
            "plan_executed": bool(execution.get("executed")),
            "plan_element_minimum_met": len(plan["elements"]) >= 50,
            "all_required_text_matches": all(text_matches.values()),
            "all_palette_samples_match": all(color_matches.values()),
            "all_required_groups_present": expected_groups.issubset(actual_names),
            "distinct_operation_minimum_met": len(distinct_operations) >= 15,
            "zero_failed_operations": not failed_operations,
            "artifacts_nonempty": artifacts_ok,
        }

        document_and_artifacts = (
            (5 if checks["connected"] and checks["page_size_matches"] else 0)
            + (5 if cdr_path.stat().st_size > 0 else 0)
            + (5 if pdf_path.stat().st_size > 0 else 0)
        )
        content_fidelity = (
            (8 if checks["all_required_text_matches"] else 0)
            + (6 if checks["all_palette_samples_match"] else 0)
            + (3 if checks["all_required_groups_present"] else 0)
            + (3 if checks["plan_element_minimum_met"] else 0)
        )
        tool_execution = (
            (8 if checks["zero_failed_operations"] else 0)
            + (7 if checks["distinct_operation_minimum_met"] else 0)
            + (5 if checks["plan_validation_ready"] and checks["plan_preview_ready"] and checks["plan_executed"] else 0)
            + (5 if text_readback and color_samples and objects["object_count"] > 0 else 0)
        )
        automated_score = document_and_artifacts + content_fidelity + tool_execution

        result = {
            "benchmark_id": spec["benchmark_id"],
            "run_id": run_id,
            "status": "AUTOMATED_PASS" if automated_score == 60 and all(checks.values()) else "AUTOMATED_REVIEW_REQUIRED",
            "expected": spec["desired_output"],
            "actual": {
                "corel_version": status.get("version"),
                "corel_version_build": status.get("version_build"),
                "page_inches": {"width": bounds["width"], "height": bounds["height"]},
                "plan_elements": len(plan["elements"]),
                "top_level_objects_after_grouping": objects["total_on_page"],
                "distinct_operations": distinct_operations,
                "distinct_operation_count": len(distinct_operations),
                "failed_operation_count": len(failed_operations),
                "text_readback": text_readback,
                "text_matches": text_matches,
                "color_samples": color_samples,
                "color_matches": color_matches,
                "required_groups_present": sorted(expected_groups.intersection(actual_names)),
                "cdr_bytes": cdr_path.stat().st_size,
                "pdf_bytes": pdf_path.stat().st_size,
            },
            "checks": checks,
            "scores": {
                "document_and_artifacts": document_and_artifacts,
                "content_fidelity": content_fidelity,
                "tool_execution_and_readback": tool_execution,
                "automated_total": automated_score,
                "visual_review": None,
                "final_total": None,
            },
            "artifacts": {
                "cdr": str(cdr_path),
                "pdf": str(pdf_path),
                "result_json": str(result_path),
            },
            "tool_trace": trace,
        }
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        print(f"Benchmark status: {result['status']}")
        print(f"Automated score: {automated_score}/60")
        print(f"Plan elements: {len(plan['elements'])}")
        print(f"Distinct operations: {len(distinct_operations)}")
        print(f"Failed operations: {len(failed_operations)}")
        print(f"CDR: {cdr_path} ({cdr_path.stat().st_size:,} bytes)")
        print(f"PDF: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
        print(f"Result: {result_path}")
        return 0 if result["status"] == "AUTOMATED_PASS" else 1
    except Exception as exc:
        failure_result = {
            "benchmark_id": spec["benchmark_id"],
            "run_id": run_id,
            "status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "artifacts": {
                "cdr": str(cdr_path) if cdr_path.exists() else None,
                "pdf": str(pdf_path) if pdf_path.exists() else None,
                "result_json": str(result_path),
            },
            "tool_trace": trace,
        }
        result_path.write_text(json.dumps(failure_result, indent=2), encoding="utf-8")
        print(f"Benchmark failed: {failure_result['error']}")
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
