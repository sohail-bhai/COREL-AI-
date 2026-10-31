"""Comprehensive End-to-End Verification exercising all CorelDRAW AI Operator tools."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from pprint import pprint

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pythoncom
from corel_operator.corel_bridge import CorelBridge
from corel_operator.workflows import calculate_sheet_layout, build_chest_number_sequence
from corel_operator.design_plans import validate_design_plan, preview_design_plan


def run_comprehensive_e2e() -> dict[str, any]:
    pythoncom.CoInitialize()
    bridge = CorelBridge()
    results: dict[str, any] = {"steps_passed": 0, "steps_failed": 0, "step_details": []}

    temp_dir = Path(tempfile.mkdtemp(prefix="corel_all_tools_test_"))
    cdr_output = temp_dir / "all_tools_verified.cdr"
    pdf_output = temp_dir / "all_tools_verified.pdf"
    svg_fixture = temp_dir / "test_sponsor_logo.svg"

    svg_fixture.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
        '<circle cx="50" cy="50" r="40" fill="#228833"/>'
        '<text x="50" y="55" font-size="14" text-anchor="middle" fill="#ffffff" font-family="Arial">AI</text>'
        '</svg>',
        encoding="utf-8",
    )

    def step(name: str, fn):
        t0 = time.perf_counter()
        try:
            res = fn()
            dur = (time.perf_counter() - t0) * 1000
            results["steps_passed"] += 1
            results["step_details"].append({"name": name, "status": "PASS", "duration_ms": round(dur, 2)})
            print(f"[PASS] {name} ({dur:.1f}ms)")
            return res
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            results["steps_failed"] += 1
            results["step_details"].append({"name": name, "status": "FAIL", "duration_ms": round(dur, 2), "error": str(exc)})
            print(f"[FAIL] {name}: {exc}")
            raise

    doc = None
    try:
        # 1. Connection & status
        status = step("1. corel_status", bridge.connect)
        assert status["connected"] is True, "Must be connected"

        # 2. Pure layout & batch sequence tools
        layout = step("2. calculate_sheet_layout", lambda: calculate_sheet_layout(item_width_inches=3.5, item_height_inches=2.0, sheet_width_inches=8.5, sheet_height_inches=11.0, margin_inches=0.5, gutter_inches=0.25))
        assert layout["capacity"] >= 2, "Layout fits should be calculated"

        batch_plan = step("3. plan_chest_number_batch", lambda: build_chest_number_sequence(1, 4, item_width_inches=3.5, item_height_inches=2.0, sheet_width_inches=8.5, sheet_height_inches=11.0))
        assert len(batch_plan["items"]) == 4, "Batch plan items generated"

        # 3. Document listing prior to creation
        docs_before = step("4. list_open_documents", bridge.list_open_documents)

        # 4. Create document & bind target
        created = step("5. create_document", lambda: bridge.create_document(8.5, 11.0))
        bound = step("6. use_active_document", lambda: bridge.use_active_document(confirm_existing_document=True))
        doc = bridge.target_doc

        # 5. Inspection tools
        doc_info = step("7. get_document_info", bridge.get_document_info)
        pages = step("8. list_pages", bridge.list_pages)
        page_bounds = step("9. get_page_bounds", lambda: bridge.get_page_bounds(1))
        layers = step("10. list_layers", lambda: bridge.list_layers(1))

        # 6. Primitive shapes
        rect = step("11. draw_rectangle", lambda: bridge.draw_rectangle(0.5, 0.5, 7.5, 10.0, "Page_Border"))
        ellipse = step("12. draw_ellipse", lambda: bridge.draw_ellipse(3.25, 7.5, 2.0, 2.0, "Hero_Circle"))
        txt = step("13. add_text", lambda: bridge.add_text("RUN FOR CHARITY 2026", 1.5, 6.5, size_pt=26, font="Arial", bold=True, object_name="Main_Title"))

        # 7. Appearance & Styling
        fill_res = step("14. set_fill_color", lambda: bridge.set_fill_color(240, 245, 255, object_name="Page_Border"))
        outline_res = step("15. set_outline", lambda: bridge.set_outline(30, 80, 160, width_points=2.5, object_name="Page_Border"))
        step("15b. set_ellipse_fill", lambda: bridge.set_fill_color(230, 60, 60, object_name="Hero_Circle"))

        # 8. Transformations & Editing
        moved = step("16. move_object", lambda: bridge.move_object(1.2, 6.2, object_name="Main_Title"))
        resized = step("17. resize_object", lambda: bridge.resize_object(2.5, 2.5, keep_aspect_ratio=True, object_name="Hero_Circle"))
        text_edited = step("18. set_text_content", lambda: bridge.set_text_content("GRAND RUN FOR CHARITY 2026", object_name="Main_Title"))
        renamed = step("19. rename_object", lambda: bridge.rename_object("Event_Header_Text", object_name="Main_Title"))
        duplicated = step("20. duplicate_object", lambda: bridge.duplicate_object(0.3, -0.3, object_name="Hero_Circle", new_name="Circle_Accent"))

        # 9. Alignment & Grouping
        align_res = step("21. align_objects", lambda: bridge.align_objects(["Hero_Circle", "Circle_Accent"], horizontal="center", vertical="center", align_to="last_selected"))
        grouped = step("22. group_shapes", lambda: bridge.group_shapes(["Hero_Circle", "Circle_Accent"], group_name="Hero_Badge_Group"))
        page_align = step("23. align_to_page", lambda: bridge.align_to_page(["Hero_Badge_Group"], horizontal="center", align_as_group=True))

        # Test ungroup on temporary objects
        step("24a. draw_temp1", lambda: bridge.draw_rectangle(1.0, 1.0, 1.0, 1.0, "Temp_A"))
        step("24b. draw_temp2", lambda: bridge.draw_rectangle(2.0, 1.0, 1.0, 1.0, "Temp_B"))
        step("24c. group_temp", lambda: bridge.group_shapes(["Temp_A", "Temp_B"], "Temp_Group"))
        ungroup_res = step("24. ungroup_shapes", lambda: bridge.ungroup_shapes(object_name="Temp_Group"))
        assert ungroup_res["ungrouped"] is True

        # 10. Import Artwork
        import_res = step("25. import_artwork", lambda: bridge.import_artwork(str(svg_fixture), "Sponsor_Badge"))
        step("25b. move_imported", lambda: bridge.move_object(0.75, 8.5, object_name="Sponsor_Badge"))

        # 11. Mutating batch creation (Option A)
        batch_created = step(
            "26. create_chest_number_batch",
            lambda: bridge.create_chest_number_batch(
                start=1, end=2, item_width_inches=3.0, item_height_inches=1.8,
                zero_pad_width=3, font="Arial", font_size_points=36.0,
                draw_border=True, header_text="MARATHON 2026"
            )
        )
        assert batch_created["created_count"] == 2

        # 12. Structured Design Plan Engine (Option B)
        card_plan = {
            "version": "1.0",
            "name": "Live Verified Banner",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0, "unit": "inch"},
            "elements": [
                {
                    "id": "banner_rect",
                    "type": "rectangle",
                    "x_inches": 1.0,
                    "y_inches": 0.8,
                    "width_inches": 6.5,
                    "height_inches": 0.8,
                    "fill": {"red": 20, "green": 50, "blue": 100},
                    "outline": {"red": 255, "green": 255, "blue": 255, "width_points": 1.0},
                },
                {
                    "id": "banner_text",
                    "type": "text",
                    "x_inches": 1.5,
                    "y_inches": 1.0,
                    "text": "OFFICIAL CERTIFIED FINISHER BANNER",
                    "font": "Arial",
                    "font_size_points": 14.0,
                    "bold": True,
                    "fill": {"red": 255, "green": 255, "blue": 255},
                },
            ],
            "validations": {"expected_element_count": 2, "bounding_box_within_canvas": True},
        }
        plan_valid = step("27. validate_design_plan", lambda: validate_design_plan(card_plan))
        assert plan_valid["ready_for_execution"] is True

        plan_prev = step("28. preview_design_plan", lambda: preview_design_plan(card_plan))
        assert plan_prev["ready_for_execution"] is True

        plan_exec = step("29. execute_design_plan", lambda: bridge.execute_design_plan(card_plan, rollback_on_failure=True))
        assert plan_exec["executed"] is True
        assert plan_exec["post_execution_verification"] is True

        # 13. Object enumeration and inspection
        objs = step("30. list_objects", lambda: bridge.list_objects(100))
        obj_info = step("31. get_object_info", lambda: bridge.get_object_info(object_name="Event_Header_Text"))
        assert obj_info["object"]["object_name"] == "Event_Header_Text"

        # 14. Persistence & Export
        save_res = step("32. save_document", lambda: bridge.save_document(str(cdr_output)))
        assert cdr_output.is_file(), "Saved CDR file must exist"
        assert cdr_output.stat().st_size > 0, "CDR file must not be empty"

        export_res = step("33. export_pdf", lambda: bridge.export_pdf(str(pdf_output)))
        assert pdf_output.is_file(), "Exported PDF file must exist"
        assert pdf_output.stat().st_size > 0, "PDF file must not be empty"

        results["cdr_file"] = {
            "path": str(cdr_output),
            "size_bytes": cdr_output.stat().st_size,
        }
        results["pdf_file"] = {
            "path": str(pdf_output),
            "size_bytes": pdf_output.stat().st_size,
        }
        results["total_objects_created"] = objs["total_on_page"]

        workspace_output = ROOT / "output"
        workspace_output.mkdir(exist_ok=True)
        shutil.copy2(cdr_output, workspace_output / "all_tools_verified.cdr")
        shutil.copy2(pdf_output, workspace_output / "all_tools_verified.pdf")

        print(f"\nSUCCESS: Generated CDR file: {cdr_output} ({cdr_output.stat().st_size:,} bytes)")
        print(f"SUCCESS: Generated PDF file: {pdf_output} ({pdf_output.stat().st_size:,} bytes)")
        print(f"Copied to workspace output folder: {workspace_output}")
        print(f"Total objects on page: {objs['total_on_page']}")

    finally:
        if doc is not None:
            try:
                doc.Close()
                time.sleep(0.5)
                print("Document closed cleanly.")
            except Exception as e:
                print(f"Cleanup close warning: {e}")
        pythoncom.CoUninitialize()

    return results


if __name__ == "__main__":
    res = run_comprehensive_e2e()
    print("\nSummary of all tools tested:")
    for d in res["step_details"]:
        print(f"  - {d['name']}: {d['status']} ({d['duration_ms']} ms)")
