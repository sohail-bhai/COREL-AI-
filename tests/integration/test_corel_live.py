from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from corel_operator.corel_bridge import CorelBridge, CorelBridgeError
from corel_operator.errors import ErrorCode


LIVE_ENABLED = os.environ.get("COREL_LIVE_TESTS") == "1"
MUTATION_ENABLED = LIVE_ENABLED and os.environ.get("COREL_LIVE_MUTATION_TESTS") == "1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = PROJECT_ROOT / "docs" / "test-reports"
TEMP_ROOT = Path(tempfile.gettempdir()) / "opencode" / "corel-live"


@unittest.skipUnless(
    LIVE_ENABLED,
    "Set COREL_LIVE_TESTS=1 explicitly to run read-only tests against CorelDRAW X7.",
)
class CorelReadOnlyLiveTests(unittest.TestCase):
    def test_status_reports_x7_without_binding_a_target(self) -> None:
        bridge = CorelBridge()
        status = bridge.connect()

        self.assertTrue(status["connected"])
        self.assertEqual(status["version_major"], 17)
        self.assertFalse(status["target_document_bound"])
        documents = bridge.list_open_documents()["documents"]
        self.assertTrue(all(not document["is_bound_target"] for document in documents))


@unittest.skipUnless(
    MUTATION_ENABLED,
    "Set both COREL_LIVE_TESTS=1 and COREL_LIVE_MUTATION_TESTS=1 to authorize a disposable-document regression.",
)
class CorelDisposableDocumentLiveTests(unittest.TestCase):
    """Exercise all mutating bridge operations only against a newly created document."""

    def setUp(self) -> None:
        import pythoncom  # type: ignore

        pythoncom.CoInitialize()
        self.pythoncom = pythoncom
        self.bridge = CorelBridge()
        self.steps: list[dict[str, Any]] = []
        self.cleanup_notes: list[str] = []
        self.status: dict[str, Any] = {}
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.output_dir = Path(tempfile.mkdtemp(prefix=f"run-{stamp}-", dir=TEMP_ROOT))
        self.cdr_path = self.output_dir / "disposable-regression.cdr"
        self.pdf_path = self.output_dir / "disposable-regression.pdf"
        self.svg_path = self.output_dir / "synthetic-import.svg"

    def tearDown(self) -> None:
        try:
            self._close_saved_target_if_needed()
        finally:
            self.pythoncom.CoUninitialize()

    def _step(self, name: str, operation: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        try:
            result = operation()
        except BaseException as exc:
            self.steps.append({
                "name": name,
                "status": "failed",
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "detail": f"{type(exc).__name__}: {exc}",
            })
            raise
        self.steps.append({
            "name": name,
            "status": "passed",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "detail": self._result_summary(result),
        })
        return result

    @staticmethod
    def _result_summary(result: Any) -> str:
        if not isinstance(result, dict):
            return type(result).__name__
        useful_keys = (
            "target_document_name", "object_name", "object_count", "path", "bytes",
            "created", "updated", "moved", "resized", "renamed", "duplicated", "imported",
        )
        parts = [f"{key}={result[key]!r}" for key in useful_keys if key in result]
        return ", ".join(parts) or "completed"

    def _write_svg_fixture(self) -> None:
        self.svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
            '<rect x="8" y="8" width="80" height="80" fill="#3366cc"/>'
            '</svg>',
            encoding="utf-8",
        )

    def _close_saved_target_if_needed(self) -> None:
        doc = self.bridge.target_doc
        if doc is None:
            return
        saved_cdrs = list(self.output_dir.glob("*.cdr")) if self.output_dir.is_dir() else []
        if not saved_cdrs and not self.cdr_path.is_file():
            try:
                self.bridge.save_document(str(self.cdr_path))
                self.cleanup_notes.append("Saved the disposable document during cleanup before closing it.")
            except Exception as exc:
                self.cleanup_notes.append(
                    f"Document left open because cleanup save failed: {type(exc).__name__}: {exc}"
                )
                return
        try:
            doc.Close()
            self.bridge.target_doc = None
            self.cleanup_notes.append("Closed the saved disposable document.")
            time.sleep(0.5)
        except Exception as exc:
            self.cleanup_notes.append(f"Saved disposable document could not be closed: {type(exc).__name__}: {exc}")

    def _write_report(self, passed: bool, failure: str | None) -> Path:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S%fZ")
        report_path = REPORT_DIR / f"{stamp}-x7-disposable-regression.md"
        cdr_artifacts = sorted(self.output_dir.glob("*.cdr"))
        pdf_artifacts = sorted(self.output_dir.glob("*.pdf"))
        artifact_lines = (
            [f"- CDR: `{path}` ({path.stat().st_size} bytes)" for path in cdr_artifacts]
            or ["- CDR: not generated"]
        )
        artifact_lines.extend(
            [f"- PDF: `{path}` ({path.stat().st_size} bytes)" for path in pdf_artifacts]
            or ["- PDF: not generated"]
        )
        artifact_lines.append(f"- Synthetic SVG fixture: `{self.svg_path}`")
        manual_review_lines = [
            "- Open each generated CDR and confirm objects remain editable."
            if cdr_artifacts else "- No CDR was generated; CDR editability review is not applicable.",
            "- Inspect each generated PDF for page size, fonts, colors, and rendering."
            if pdf_artifacts else "- No PDF was generated; PDF review is not applicable.",
            "- Do not mark tools live-verified until this report and the artifacts have been reviewed.",
        ]
        rows = [
            f"| {item['name']} | {item['status']} | {item['duration_ms']} | {str(item['detail']).replace('|', '/')} |"
            for item in self.steps
        ]
        corel_version = self.status.get("version", "unknown")
        lines = [
            "# CorelDRAW X7 Disposable-Document Regression",
            "",
            f"- **UTC run time:** {stamp}",
            f"- **Result:** {'PASS' if passed else 'FAIL'}",
            f"- **CorelDRAW version:** {corel_version}",
            f"- **ProgID:** {self.status.get('prog_id_used', 'unknown')}",
            f"- **Connection mode:** {self.status.get('connection_mode', 'unknown')}",
            f"- **Output directory:** `{self.output_dir}`",
            f"- **Failure:** {failure or 'None'}",
            "",
            "The run created a new synthetic document and did not bind a document that predated the test.",
            "Passing this regression is evidence for the tested environment only; it does not prove visual or print readiness.",
            "",
            "| Step | Status | Duration (ms) | Detail |",
            "|---|---|---:|---|",
            *rows,
            "",
            "## Artifacts",
            "",
            *artifact_lines,
            "",
            "## Cleanup",
            "",
            *(f"- {note}" for note in self.cleanup_notes),
            "",
            "## Manual review still required",
            "",
            *manual_review_lines,
        ]
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report_path

    def test_existing_tools_on_new_disposable_document(self) -> None:
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            self.assertEqual(self.status["version_major"], 17)

            created = self._step("create_document", lambda: self.bridge.create_document(8.5, 11.0))
            self.assertTrue(created["created"])
            self.assertAlmostEqual(created["actual_page_size_inches"]["width"], 8.5, delta=0.01)
            self.assertAlmostEqual(created["actual_page_size_inches"]["height"], 11.0, delta=0.01)

            bound = self._step("use_active_document", lambda: self.bridge.use_active_document(True))
            self.assertEqual(bound["target_document_name"], created["target_document_name"])

            rectangle = self._step(
                "draw_rectangle", lambda: self.bridge.draw_rectangle(0.75, 7.5, 3.0, 1.5, "Live_Rectangle")
            )
            self.assertAlmostEqual(rectangle["actual_bounds_inches"]["width"], 3.0, delta=0.01)
            ellipse = self._step(
                "draw_ellipse", lambda: self.bridge.draw_ellipse(4.25, 7.5, 2.0, 1.5, "Live_Ellipse")
            )
            self.assertAlmostEqual(ellipse["actual_bounds_inches"]["height"], 1.5, delta=0.01)
            text = self._step(
                "add_text", lambda: self.bridge.add_text("LIVE TEST 001", 1.0, 5.5, 24, "Arial", True, "Live_Text")
            )
            self.assertEqual(text["actual_text"]["text"], "LIVE TEST 001")

            fill = self._step(
                "set_fill_color", lambda: self.bridge.set_fill_color(40, 120, 200, object_name="Live_Rectangle")
            )
            self.assertEqual(fill["actual_fill"]["type"], "uniform")
            outline = self._step(
                "set_outline", lambda: self.bridge.set_outline(20, 30, 40, 1.0, object_name="Live_Rectangle")
            )
            self.assertTrue(outline["actual_outline"]["present"])
            moved = self._step(
                "move_object", lambda: self.bridge.move_object(4.0, 7.0, object_name="Live_Ellipse")
            )
            self.assertAlmostEqual(moved["x_inches"], 4.0, delta=0.01)
            resized = self._step(
                "resize_object", lambda: self.bridge.resize_object(2.5, 1.25, False, object_name="Live_Ellipse")
            )
            self.assertAlmostEqual(resized["new_size_inches"][0], 2.5, delta=0.01)
            edited = self._step(
                "set_text_content", lambda: self.bridge.set_text_content("LIVE TEST 002", object_name="Live_Text")
            )
            self.assertEqual(edited["new_text"], "LIVE TEST 002")
            renamed = self._step(
                "rename_object", lambda: self.bridge.rename_object("Live_Ellipse_Renamed", object_name="Live_Ellipse")
            )
            self.assertEqual(renamed["object_name"], "Live_Ellipse_Renamed")
            duplicated = self._step(
                "duplicate_object",
                lambda: self.bridge.duplicate_object(0.25, -0.25, object_name="Live_Rectangle", new_name="Live_Rectangle_Copy"),
            )
            self.assertEqual(duplicated["object_name"], "Live_Rectangle_Copy")

            self._step("create synthetic import fixture", self._write_svg_fixture)
            imported = self._step(
                "import_artwork", lambda: self.bridge.import_artwork(str(self.svg_path), "Live_Import")
            )
            self.assertGreaterEqual(imported["object_count"], 1)
            objects = self._step("list_objects", lambda: self.bridge.list_objects(50))
            names = {item["object_name"] for item in objects["objects"]}
            self.assertTrue({"Live_Rectangle", "Live_Rectangle_Copy", "Live_Ellipse_Renamed", "Live_Text"} <= names)

            exported = self._step("export_pdf", lambda: self.bridge.export_pdf(str(self.pdf_path)))
            self.assertGreater(exported["bytes"], 0)
            saved = self._step("save_document", lambda: self.bridge.save_document(str(self.cdr_path)))
            self.assertGreater(saved["bytes"], 0)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            report = self._write_report(passed, failure)
            print(f"Live regression report: {report}")

    def test_create_chest_number_batch_live(self) -> None:
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            created = self._step("create_document", lambda: self.bridge.create_document(8.5, 11.0))
            self.assertTrue(created["created"])

            batch = self._step(
                "create_chest_number_batch",
                lambda: self.bridge.create_chest_number_batch(
                    start=1,
                    end=4,
                    item_width_inches=3.5,
                    item_height_inches=2.2,
                    zero_pad_width=3,
                    font="Arial",
                    font_size_points=48.0,
                    draw_border=True,
                    header_text="MARATHON 2026",
                ),
            )
            self.assertEqual(batch["created_count"], 4)
            self.assertEqual(len(batch["items"]), 4)

            objects = self._step("list_objects", lambda: self.bridge.list_objects(50))
            names = {item["object_name"] for item in objects["objects"]}
            self.assertIn("chest_number_001_box", names)
            self.assertIn("chest_number_001_number", names)
            self.assertIn("chest_number_001_header", names)

            batch_cdr = self.output_dir / "disposable-chest-numbers.cdr"
            saved = self._step("save_document", lambda: self.bridge.save_document(str(batch_cdr)))
            self.assertGreater(saved["bytes"], 0)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            report = self._write_report(passed, failure)
            print(f"Live chest-number report: {report}")

    def test_execute_design_plan_live(self) -> None:
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            created = self._step("create_document", lambda: self.bridge.create_document(8.5, 11.0))
            self.assertTrue(created["created"])

            plan = {
                "version": "1.0",
                "name": "Live Event Badge",
                "canvas": {"width_inches": 8.5, "height_inches": 11.0},
                "elements": [
                    {
                        "id": "badge_card",
                        "type": "rectangle",
                        "x_inches": 1.0,
                        "y_inches": 6.0,
                        "width_inches": 4.0,
                        "height_inches": 2.5,
                        "fill": {"red": 30, "green": 90, "blue": 180},
                        "outline": {"red": 255, "green": 255, "blue": 255, "width_points": 2.0},
                    },
                    {
                        "id": "badge_icon_circle",
                        "type": "ellipse",
                        "x_inches": 1.5,
                        "y_inches": 6.5,
                        "width_inches": 1.5,
                        "height_inches": 1.5,
                        "fill": {"red": 240, "green": 240, "blue": 240},
                    },
                    {
                        "id": "badge_title",
                        "type": "text",
                        "x_inches": 1.2,
                        "y_inches": 7.8,
                        "text": "VIP ACCESS",
                        "font": "Arial",
                        "font_size_points": 18.0,
                        "bold": True,
                        "fill": {"red": 255, "green": 255, "blue": 255},
                    },
                ],
                "validations": {"expected_element_count": 3},
            }

            result = self._step("execute_design_plan", lambda: self.bridge.execute_design_plan(plan))
            self.assertTrue(result["executed"])
            self.assertEqual(result["elements_executed"], 3)
            self.assertTrue(result["post_execution_verification"])
            self.assertEqual(len(result["discrepancies"]), 0)

            objects = self._step("list_objects", lambda: self.bridge.list_objects(50))
            names = {item["object_name"] for item in objects["objects"]}
            self.assertIn("badge_card", names)
            self.assertIn("badge_icon_circle", names)
            self.assertIn("badge_title", names)

            # Test live command-group Undo with a deterministic bridge failure after
            # the first CorelDRAW mutation. The asset itself passes path preflight.
            self._write_svg_fixture()
            failing_plan = {
                "version": "1.0",
                "name": "Live Failing Plan",
                "canvas": {"width_inches": 8.5, "height_inches": 11.0},
                "elements": [
                    {
                        "id": "rollback_rect",
                        "type": "rectangle",
                        "x_inches": 5.5,
                        "y_inches": 6.0,
                        "width_inches": 2.0,
                        "height_inches": 2.0,
                    },
                    {
                        "id": "rollback_artwork_fail",
                        "type": "artwork",
                        "file_path": str(self.svg_path),
                    },
                ],
            }
            original_import_artwork = self.bridge.import_artwork

            def force_import_failure(file_path: str, object_name: str = "AI_Artwork") -> dict[str, Any]:
                raise CorelBridgeError("Synthetic post-preflight failure.", ErrorCode.COREL_COM_ERROR)

            self.bridge.import_artwork = force_import_failure  # type: ignore[method-assign]
            try:
                with self.assertRaises(CorelBridgeError) as rollback_context:
                    self._step("execute_failing_plan_rollback", lambda: self.bridge.execute_design_plan(failing_plan))
            finally:
                self.bridge.import_artwork = original_import_artwork  # type: ignore[method-assign]
            self.assertTrue(rollback_context.exception.details["rollback"]["verified"])

            # Verify that rollback_rect was rolled back and is not on page
            after_rollback = self._step("list_objects_after_rollback", lambda: self.bridge.list_objects(50))
            after_names = {item["object_name"] for item in after_rollback["objects"]}
            self.assertNotIn("rollback_rect", after_names)
            # Original shapes should still remain
            self.assertIn("badge_card", after_names)

            plan_cdr = self.output_dir / "disposable-design-plan.cdr"
            saved = self._step("save_document", lambda: self.bridge.save_document(str(plan_cdr)))
            self.assertGreater(saved["bytes"], 0)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            report = self._write_report(passed, failure)
            print(f"Live design-plan report: {report}")

    def test_align_and_group_live(self) -> None:
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            created = self._step("create_document", lambda: self.bridge.create_document(8.5, 11.0))
            self.assertTrue(created["created"])

            # 1. Create shapes to manipulate
            b1 = self._step(
                "draw_box_1",
                lambda: self.bridge.draw_rectangle(1.0, 2.0, 2.0, 1.0, "Align_Box1"),
            )
            b2 = self._step(
                "draw_box_2",
                lambda: self.bridge.draw_rectangle(4.0, 6.0, 2.0, 1.0, "Align_Box2"),
            )
            self.assertEqual(b1["object_name"], "Align_Box1")
            self.assertEqual(b2["object_name"], "Align_Box2")

            # 2. Test align_objects: align left to last_selected (Align_Box2 at x=4.0)
            aligned = self._step(
                "align_objects",
                lambda: self.bridge.align_objects(["Align_Box1", "Align_Box2"], horizontal="left", align_to="last_selected"),
            )
            self.assertTrue(aligned["aligned"])
            b1_bounds = next(o["bounds_inches"] for o in aligned["objects"] if o["object_name"] == "Align_Box1")
            self.assertAlmostEqual(b1_bounds["x"], 4.0, delta=0.02)

            # 3. Test align_to_page: center Align_Box1 on page
            page_aligned = self._step(
                "align_to_page",
                lambda: self.bridge.align_to_page(["Align_Box1"], horizontal="center", vertical="center"),
            )
            self.assertTrue(page_aligned["aligned"])
            b1_centered = next(o["bounds_inches"] for o in page_aligned["objects"] if o["object_name"] == "Align_Box1")
            expected_x = (8.5 - 2.0) / 2.0
            expected_y = (11.0 - 1.0) / 2.0
            self.assertAlmostEqual(b1_centered["x"], expected_x, delta=0.02)
            self.assertAlmostEqual(b1_centered["y"], expected_y, delta=0.02)

            # 4. Test group_shapes
            grouped = self._step(
                "group_shapes",
                lambda: self.bridge.group_shapes(["Align_Box1", "Align_Box2"], group_name="Live_Group"),
            )
            self.assertTrue(grouped["grouped"])
            self.assertEqual(grouped["group_name"], "Live_Group")
            self.assertEqual(grouped["shape_count"], 2)

            objects_after_group = self._step("list_objects_after_group", lambda: self.bridge.list_objects(50))
            group_names = {item["object_name"] for item in objects_after_group["objects"]}
            self.assertIn("Live_Group", group_names)

            # 5. Test ungroup_shapes
            ungrouped = self._step(
                "ungroup_shapes",
                lambda: self.bridge.ungroup_shapes(object_name="Live_Group", ungroup_all=False),
            )
            self.assertTrue(ungrouped["ungrouped"])
            self.assertEqual(ungrouped["shapes_released"], 2)

            objects_after_ungroup = self._step("list_objects_after_ungroup", lambda: self.bridge.list_objects(50))
            final_names = {item["object_name"] for item in objects_after_ungroup["objects"]}
            self.assertIn("Align_Box1", final_names)
            self.assertIn("Align_Box2", final_names)
            self.assertNotIn("Live_Group", final_names)

            align_cdr = self.output_dir / "disposable-align-group.cdr"
            saved = self._step("save_document", lambda: self.bridge.save_document(str(align_cdr)))
            self.assertGreater(saved["bytes"], 0)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            report = self._write_report(passed, failure)
            print(f"Live align-group report: {report}")



if __name__ == "__main__":
    unittest.main()
