from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from corel_operator.corel_bridge import CorelBridge


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
        if not self.cdr_path.is_file():
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
        except Exception as exc:
            self.cleanup_notes.append(f"Saved disposable document could not be closed: {type(exc).__name__}: {exc}")

    def _write_report(self, passed: bool, failure: str | None) -> Path:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S%fZ")
        report_path = REPORT_DIR / f"{stamp}-x7-disposable-regression.md"
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
            f"- CDR: `{self.cdr_path}` ({self.cdr_path.stat().st_size if self.cdr_path.is_file() else 'missing'} bytes)",
            f"- PDF: `{self.pdf_path}` ({self.pdf_path.stat().st_size if self.pdf_path.is_file() else 'missing'} bytes)",
            f"- Synthetic SVG fixture: `{self.svg_path}`",
            "",
            "## Cleanup",
            "",
            *(f"- {note}" for note in self.cleanup_notes),
            "",
            "## Manual review still required",
            "",
            "- Open the CDR and confirm objects remain editable.",
            "- Inspect the PDF page size, fonts, colors, and rendering.",
            "- Do not mark tools live-verified until this report and the artifacts have been reviewed.",
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


if __name__ == "__main__":
    unittest.main()
