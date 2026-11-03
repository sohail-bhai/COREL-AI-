from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

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
            "scanned_objects", "scanned_entries", "truncated", "incomplete_reasons",
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

    def _create_asymmetric_imposition_fixture(self) -> dict[str, Any]:
        """Create one synthetic grouped repeat without reading or importing user artwork."""
        doc = self.bridge.target_doc
        app = self.bridge.app
        if doc is None or app is None:
            raise AssertionError("A bridge-created target document is required for the fixture.")
        points = [
            (0.25, 0.25),
            (4.25, 0.25),
            (4.25, 2.25),
            (1.25, 2.25),
            (1.25, 4.25),
            (0.25, 4.25),
        ]
        with self.bridge._in_inches(doc), self.bridge._reference_point(doc, self.bridge.CDR_BOTTOM_LEFT):
            curve = app.CreateCurve(doc)
            subpath = curve.CreateSubPath(*points[0])
            for x, y in points[1:]:
                subpath.AppendLineSegment(x, y)
            subpath.Closed = True
            dieline = doc.ActivePage.ActiveLayer.CreateCurve(curve)
            dieline.Name = "CutContour"
        artwork = self.bridge.draw_rectangle(0.4, 0.4, 0.6, 0.6, "Repeat_Artwork")
        grouped = self.bridge.group_shapes(
            [artwork["object_name"], "CutContour"],
            group_name="Repeat_Unit",
        )
        return {
            "grouped": grouped["grouped"],
            "group_name": grouped["group_name"],
            "child_names": grouped["child_names"],
            "point_count": len(points),
        }

    def _close_saved_target_if_needed(self) -> None:
        doc = self.bridge.target_doc
        if doc is None:
            return
        saved_cdrs = list(self.output_dir.glob("*.cdr")) if self.output_dir.is_dir() else []
        try:
            needs_save = not saved_cdrs or bool(doc.Dirty)
        except Exception:
            self.cleanup_notes.append("Disposable document left open because its dirty state could not be read.")
            return
        if needs_save:
            checkpoint = self.cdr_path
            if checkpoint.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                checkpoint = self.output_dir / f"cleanup-{stamp}.cdr"
            try:
                self.bridge.save_document(str(checkpoint))
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

    def test_vector_editing_and_shaping_live(self) -> None:
        """Deferred native curve, node/handle and source-preserving shaping gate."""
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create vector fixture",lambda:self.bridge.create_document(8.5,11))
            paths=[{'start':{'x':1,'y':1},'closed':True,'segments':[
                {'type':'line','end':{'x':3,'y':1}},{'type':'line','end':{'x':3,'y':3}},
                {'type':'line','end':{'x':1,'y':3}}]},
                {'start':{'x':4,'y':1},'closed':False,'segments':[
                    {'type':'cubic','control1':{'x':4,'y':3},'control2':{'x':6,'y':3},'end':{'x':6,'y':1}}]}]
            created=self._step("create_vector_path",lambda:self.bridge.create_vector_path(paths,"VectorSource"))
            reference=created["objects"][0]["object"]["object_reference"]
            inspected=self._step("get_curve_geometry",lambda:self.bridge.get_curve_geometry(object_reference=reference))
            self.assertEqual(inspected["curve"]["segment_count"],5); self.assertEqual(inspected["curve"]["node_count"],6)
            edited=self._step("edit_curve_geometry",lambda:self.bridge.edit_curve_geometry(inspected["curve"]["fingerprint"],
                node_edits=[{"subpath_index":2,"node_index":1,"position":{"x":4.25,"y":1.25}}],
                handle_edits=[{"subpath_index":2,"segment_index":1,"control2":{"x":5.75,"y":3.25}}],
                convert_edited_nodes_to_cusp=True,object_reference=reference))
            self.assertEqual(edited["curve"]["paths"][1]["start"],{"x":4.25,"y":1.25})
            self._step("vector source color",lambda:self.bridge.set_fill_color(30,80,180,object_reference=reference))
            a=self._step("boolean source rectangle",lambda:self.bridge.draw_rectangle(1,5,2,2,"BooleanSource"))
            b=self._step("boolean target rectangle",lambda:self.bridge.draw_rectangle(2,5,2,2,"BooleanTarget"))
            a_ref=self.bridge.get_object_info(object_name=a["object_name"])["object"]["object_reference"]
            b_ref=self.bridge.get_object_info(object_name=b["object_name"])["object"]["object_reference"]
            a_before=self.bridge._vector_source_signature(self.bridge.target_doc,self.bridge._find_shape(self.bridge.target_doc,object_name=a["object_name"]))
            for operation,width in (("weld",3),("trim",1),("intersect",1)):
                result=self._step("boolean_shapes "+operation,lambda:self.bridge.boolean_shapes(operation,a_ref,b_ref,"Boolean_"+operation))
                self.assertEqual(result["created_count"],1); self.assertTrue(result["source_preservation"]["verified"])
                self.assertAlmostEqual(result["objects"][0]["curve"]["bounds_inches"]["width"],width,delta=.001)
            self.assertEqual(a_before,self.bridge._vector_source_signature(self.bridge.target_doc,self.bridge._find_shape(self.bridge.target_doc,object_name=a["object_name"])))
            combined=self._step("combine_vector_shapes",lambda:self.bridge.combine_vector_shapes([reference,b_ref],"CompoundVector"))
            self.assertEqual(len(combined["objects"][0]["curve"]["paths"]),3)
            split=self._step("break_apart_curve",lambda:self.bridge.break_apart_curve(combined["objects"][0]["object"]["object_reference"],"VectorPart"))
            self.assertEqual(split["created_count"],3); self.assertTrue(split["source_preservation"]["verified"])
            closed_cubic=[{'start':{'x':1,'y':8},'closed':True,'segments':[
                {'type':'cubic','control1':{'x':1,'y':9},'control2':{'x':3,'y':9},'end':{'x':3,'y':8}},
                {'type':'cubic','control1':{'x':3,'y':7},'control2':{'x':1,'y':7},'end':{'x':1,'y':8}}]}]
            loop=self._step("closed cubic closure",lambda:self.bridge.create_vector_path(closed_cubic,"ClosedCubic"))
            self.assertEqual(loop["objects"][0]["curve"]["node_count"],2)
            self._step("save vector fixture",lambda:self.bridge.save_document(str(self.output_dir/"vector-coverage.cdr")))
            self._step("export vector fixture",lambda:self.bridge.export_pdf_controlled(str(self.output_dir/"vector-coverage.pdf")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_vector_topology_revision_live(self) -> None:
        """Deferred CopyAssign/subdivision/reconnection gate on its own fixtures."""
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create topology fixture",lambda:self.bridge.create_document(8.5,11))
            paths=[{'start':{'x':1,'y':1},'closed':True,'segments':[
                {'type':'line','end':{'x':3,'y':1}},{'type':'line','end':{'x':3,'y':3}},
                {'type':'line','end':{'x':1,'y':3}}]},
                {'start':{'x':1,'y':4},'closed':False,'segments':[
                    {'type':'cubic','control1':{'x':1,'y':6},'control2':{'x':5,'y':6},'end':{'x':5,'y':4}}]}]
            created=self._step("topology source",lambda:self.bridge.create_vector_path(paths,"TopologySource"))
            reference=created["objects"][0]["object"]["object_reference"]
            self._step("source appearance",lambda:self.bridge.set_fill_color(50,140,80,object_reference=reference))
            document=self.bridge.target_doc; source=self.bridge._find_shape(document,object_name="TopologySource")
            signature=self.bridge._vector_source_signature(document,source)
            before=self.bridge.get_curve_geometry(object_reference=reference)["curve"]
            inserted=self._step("revise_curve_topology insertion",lambda:self.bridge.revise_curve_topology(reference,before["fingerprint"],
                insertions=[{"subpath_index":2,"segment_index":1,"t":t} for t in (.25,.5,.75)],result_name="SubdividedCurve"))
            self.assertEqual(inserted["topology"]["node_count"],9)
            self.assertEqual(inserted["objects"][0]["curve"]["paths"][1]["segments"][1]["end"],{"x":3.,"y":5.5})
            self.assertEqual(self.bridge._fill_readback(self.bridge._find_shape(document,object_name="SubdividedCurve")),signature["fill"])
            deleted=self._step("revise_curve_topology deletion",lambda:self.bridge.revise_curve_topology(reference,before["fingerprint"],
                deletions=[{"subpath_index":1,"node_index":1,"replacement":{"type":"cubic","control1":{"x":1,"y":2},"control2":{"x":2,"y":1}}}],
                result_name="ReconnectedCurve"))
            self.assertEqual(deleted["topology"]["deleted_count"],1); self.assertEqual(deleted["topology"]["node_count"],5)
            self.assertEqual(self.bridge._vector_source_signature(document,source),signature)
            self._step("rotate topology source",lambda:self.bridge.rotate_object(25,object_reference=reference))
            rotated=self.bridge.get_curve_geometry(object_reference=reference)["curve"]
            self._step("rotated CopyAssign coordinates",lambda:self.bridge.revise_curve_topology(reference,rotated["fingerprint"],
                insertions=[{"subpath_index":2,"segment_index":1,"t":.5}],result_name="RotatedSubdivision"))
            box=self._step("primitive source",lambda:self.bridge.draw_rectangle(5,7,1,1,"PrimitiveTopology"))
            box_ref=self.bridge.get_object_info(object_name=box["object_name"])["object"]["object_reference"]
            geometry=self.bridge.get_curve_geometry(object_reference=box_ref)["curve"]
            primitive=self._step("primitive CopyAssign",lambda:self.bridge.revise_curve_topology(box_ref,geometry["fingerprint"],
                insertions=[{"subpath_index":1,"segment_index":1,"t":.5}],result_name="PrimitiveSubdivision"))
            self.assertEqual(primitive["objects"][0]["curve"]["node_count"],5)
            self.assertFalse(self.bridge.get_curve_geometry(object_reference=box_ref)["editable"])
            self._step("save topology fixture",lambda:self.bridge.save_document(str(self.output_dir/"vector-topology.cdr")))
            self._step("export topology fixture",lambda:self.bridge.export_pdf_controlled(str(self.output_dir/"vector-topology.pdf")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_native_process_colors_live(self) -> None:
        """Deferred native RGB/CMYK component/outline/text gate on its own fixtures."""
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create process-color fixture",lambda:self.bridge.create_document(8.5,11))
            box=self._step("color vector fixture",lambda:self.bridge.draw_rectangle(1,1,3,2,"ProcessVector"))
            reference=self.bridge.get_object_info(object_name=box["object_name"])["object"]["object_reference"]
            before=self.bridge.get_curve_geometry(object_reference=reference)["curve"]
            for color in ({"model":"rgb","red":20,"green":100,"blue":180},
                          {"model":"cmyk","cyan":80,"magenta":40,"yellow":0,"black":10}):
                result=self._step("set_process_color "+color["model"],lambda:self.bridge.set_process_color(color,object_reference=reference))
                self.assertEqual(result["actual_color"]["model"],color["model"])
                self.assertEqual(result["actual_color"]["value"],{key:value for key,value in color.items() if key!="model"})
                self.assertEqual(self.bridge.get_curve_geometry(object_reference=reference)["curve"],before)
            self._step("prepare existing ordinary outline",lambda:self.bridge.set_outline(0,0,0,1,object_reference=reference))
            shape=self.bridge._find_shape(self.bridge.target_doc,object_name=box["object_name"])
            before_outline=self.bridge._outline_readback(shape); before_fill=self.bridge._fill_readback(shape)
            outline=self._step("CMYK ordinary outline",lambda:self.bridge.set_process_color(
                {"model":"cmyk","cyan":0,"magenta":0,"yellow":0,"black":100},channel="outline",object_reference=reference))
            self.assertEqual(outline["actual_outline"]["width_raw"],before_outline["width_raw"])
            self.assertEqual(outline["actual_fill"],before_fill)
            title=self._step("process text fixture",lambda:self.bridge.add_text("Editable CMYK title",1,5,18,"Arial",True,"ProcessTitle"))
            title_ref=self.bridge.get_object_info(object_name=title["object_name"])["object"]["object_reference"]
            text_before=self.bridge.get_text_properties(object_reference=title_ref)["text"]
            self._step("CMYK text fill",lambda:self.bridge.set_process_color(
                {"model":"cmyk","cyan":0,"magenta":100,"yellow":80,"black":0},object_reference=title_ref))
            self.assertEqual(self.bridge.get_text_properties(object_reference=title_ref)["text"],text_before)
            self._step("save process colors",lambda:self.bridge.save_document(str(self.output_dir/"process-colors.cdr")))
            self._step("export process colors",lambda:self.bridge.export_pdf_controlled(str(self.output_dir/"process-colors.pdf")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_uniform_transparency_live(self) -> None:
        """Deferred normal-mode percentage/scope/removal gate on synthetic artwork."""
        from PIL import Image
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create transparency fixture",lambda:self.bridge.create_document(8.5,11))
            box=self._step("transparency vector",lambda:self.bridge.draw_rectangle(1,1,3,2,"TransparencyVector"))
            reference=self.bridge.get_object_info(object_name=box["object_name"])["object"]["object_reference"]
            self._step("base fill",lambda:self.bridge.set_process_color({"model":"rgb","red":20,"green":100,"blue":180},object_reference=reference))
            self._step("base outline",lambda:self.bridge.set_outline(0,0,0,1,object_reference=reference))
            before=self.bridge.get_curve_geometry(object_reference=reference)["curve"]
            self.assertEqual(self._step("get_transparency none",lambda:self.bridge.get_transparency(object_reference=reference))["transparency"]["type"],"none")
            for percent,scope in ((25,"fill"),(60,"outline"),(100,"both")):
                result=self._step("set_uniform_transparency "+scope,lambda:self.bridge.set_uniform_transparency(percent,scope,object_reference=reference))
                self.assertEqual(result["transparency"]["uniform_percent"],percent)
                self.assertEqual(result["transparency"]["applied_to"],scope)
                self.assertEqual(result["transparency"]["merge_mode_code"],0)
                self.assertEqual(self.bridge.get_curve_geometry(object_reference=reference)["curve"],before)
            removed=self._step("remove transparency",lambda:self.bridge.set_uniform_transparency(0,object_reference=reference))
            self.assertTrue(removed["removed"]); self.assertEqual(removed["transparency"]["type"],"none")
            title=self._step("transparency text",lambda:self.bridge.add_text("Editable transparent title",1,5,18,"Arial",True,"TransparencyTitle"))
            title_ref=self.bridge.get_object_info(object_name=title["object_name"])["object"]["object_reference"]
            text=self.bridge.get_text_properties(object_reference=title_ref)["text"]
            self._step("text transparency",lambda:self.bridge.set_uniform_transparency(35,object_reference=title_ref))
            self.assertEqual(self.bridge.get_text_properties(object_reference=title_ref)["text"],text)
            raster_path=self.output_dir/"transparency-raster.png"
            Image.new("RGB",(300,300),(50,160,90)).save(raster_path,dpi=(300,300))
            imported=self._step("synthetic transparency bitmap",lambda:self.bridge.import_artwork(str(raster_path),"TransparencyBitmap"))
            bitmap_ref=self.bridge.get_object_info(object_name=imported["object_names"][0])["object"]["object_reference"]
            bitmap=self._step("bitmap transparency",lambda:self.bridge.set_uniform_transparency(50,object_reference=bitmap_ref))
            self.assertTrue(bitmap["preservation_verified"])
            self._step("save transparency fixture",lambda:self.bridge.save_document(str(self.output_dir/"uniform-transparency.cdr")))
            self._step("export transparency fixture",lambda:self.bridge.export_pdf_controlled(str(self.output_dir/"uniform-transparency.pdf")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_contour_offsets_live(self) -> None:
        """Deferred copied closed-vector contours, native controls and separation."""
        passed = False; failure = None
        try:
            self.status = self._step("connect", self.bridge.connect)
            self._step("create contour fixture", lambda: self.bridge.create_document(8.5, 11))
            rectangle = self._step("contour rectangle", lambda: self.bridge.draw_rectangle(1, 1, 3, 2, "OffsetRectangle"))
            rect_ref = self.bridge.get_object_info(object_name=rectangle['object_name'])['object']['object_reference']
            ellipse = self._step("contour ellipse", lambda: self.bridge.draw_ellipse(5, 5, 2, 1.5, "OffsetEllipse"))
            ellipse_ref = self.bridge.get_object_info(object_name=ellipse['object_name'])['object']['object_reference']
            cubic = self._step("closed cubic source", lambda: self.bridge.create_vector_path([
                {'start': {'x': 1, 'y': 5}, 'closed': True, 'segments': [
                    {'type': 'cubic', 'control1': {'x': 1, 'y': 8}, 'control2': {'x': 4, 'y': 8}, 'end': {'x': 4, 'y': 5}},
                    {'type': 'line', 'end': {'x': 1, 'y': 5}}]}], "OffsetCubic"))
            cubic_ref = cubic['objects'][0]['object']['object_reference']
            compound = self._step("compound closed source", lambda: self.bridge.create_vector_path([
                {'start': {'x': 5, 'y': 1}, 'closed': True, 'segments': [
                    {'type': 'line', 'end': {'x': 7, 'y': 1}}, {'type': 'line', 'end': {'x': 7, 'y': 4}},
                    {'type': 'line', 'end': {'x': 5, 'y': 4}}, {'type': 'line', 'end': {'x': 5, 'y': 1}}]},
                {'start': {'x': 5.5, 'y': 2}, 'closed': True, 'segments': [
                    {'type': 'line', 'end': {'x': 5.5, 'y': 3}}, {'type': 'line', 'end': {'x': 6.5, 'y': 3}},
                    {'type': 'line', 'end': {'x': 6.5, 'y': 2}}, {'type': 'line', 'end': {'x': 5.5, 'y': 2}}]}], "OffsetCompound"))
            compound_ref = compound['objects'][0]['object']['object_reference']
            records = []
            for reference, direction in ((rect_ref, 'outside'), (ellipse_ref, 'outside'), (cubic_ref, 'inside'), (compound_ref, 'outside')):
                normalized = self._step("explicit contour fixture fill", lambda: self.bridge.set_process_color(
                    {'model': 'rgb', 'red': 80, 'green': 140, 'blue': 210}, replace_non_uniform=True, object_reference=reference))
                self.assertEqual(normalized['actual_fill']['type_code'], 1)
                outline = self._step("explicit contour fixture outline", lambda: self.bridge.set_outline(0, 0, 0, 0, object_reference=reference))
                self.assertEqual(outline['actual_outline']['type_code'], 0)
                transparency = self._step("explicit contour fixture transparency", lambda: self.bridge.set_uniform_transparency(
                    0, replace_existing=True, object_reference=reference))
                self.assertEqual(transparency['transparency']['type_code'], 0)
                before = self.bridge._offset_source_signature(self.bridge.target_doc, self.bridge._resolve_object_reference(self.bridge.target_doc, reference)[0])
                result = self._step("create_contour_offsets " + direction, lambda: self.bridge.create_contour_offsets(
                    reference, .05, direction=direction, steps=2, color={'model': 'cmyk', 'cyan': 10, 'magenta': 60, 'yellow': 80, 'black': 0},
                    result_name_prefix='NativeOffset_' + str(len(records))))
                self.assertTrue(result['source_preservation']['verified'])
                self.assertEqual(result['native_parameters']['Steps'], 2)
                self.assertGreater(result['created_count'], 0)
                self.assertEqual(self.bridge._offset_source_signature(self.bridge.target_doc, self.bridge._resolve_object_reference(self.bridge.target_doc, reference)[0]), before)
                for item in result['objects']:
                    self.assertTrue(all(path['closed'] for path in item['curve']['paths']))
                    self.assertIsNotNone(item['object']['object_reference'])
                records.append(result)
            (self.output_dir / 'contour-offset-readback.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
            self._step("save contour fixture", lambda: self.bridge.save_document(str(self.output_dir / 'contour-offsets.cdr')))
            self._step("export contour fixture", lambda: self.bridge.export_pdf_controlled(str(self.output_dir / 'contour-offsets.pdf')))
            passed = True
        except BaseException as exc:
            failure = f'{type(exc).__name__}: {exc}'; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed, failure)

    def test_gradient_fills_live(self) -> None:
        """Deferred multi-stop/types/editable-text gate with CDR/PDF artifacts."""
        from corel_operator.errors import CorelBridgeError, ErrorCode
        passed = False; failure = None
        try:
            self.status = self._step("connect", self.bridge.connect)
            self._step("create gradient fixture", lambda: self.bridge.create_document(8.5, 11))
            stops = [{'position_percent': position, 'color': {'model': 'cmyk', 'cyan': c, 'magenta': m, 'yellow': y, 'black': k}}
                     for position, (c, m, y, k) in ((0, (0, 20, 40, 0)), (40, (10, 30, 50, 0)), (100, (40, 60, 80, 10)))]
            records = []
            for index, kind in enumerate(('linear', 'radial', 'conical', 'square')):
                box = self._step("gradient " + kind + " fixture", lambda: self.bridge.draw_rectangle(
                    1 + (index % 2) * 3.5, 1 + (index // 2) * 3, 3, 2, "Gradient_" + kind))
                reference = self.bridge.get_object_info(object_name=box['object_name'])['object']['object_reference']
                geometry = self.bridge.get_curve_geometry(object_reference=reference)['curve']
                result = self._step("set_gradient_fill " + kind, lambda: self.bridge.set_gradient_fill(
                    stops, kind, angle_degrees=30., steps=128, edge_padding_percent=5,
                    center_offset_x_percent=10., center_offset_y_percent=-10., object_reference=reference))
                self.assertEqual([s['position_percent'] for s in result['fill']['gradient']['stops']], [0, 40, 100])
                self.assertEqual(result['fill']['gradient']['type'], kind)
                self.assertFalse(result['fill']['gradient']['is_transparent'])
                self.assertEqual(self.bridge.get_curve_geometry(object_reference=reference)['curve'], geometry)
                inspected = self._step("get_gradient_fill " + kind, lambda: self.bridge.get_gradient_fill(object_reference=reference))
                self.assertTrue(inspected['fill']['complete']); self.assertEqual(inspected['fingerprint'], result['fingerprint'])
                with self.assertRaises(CorelBridgeError) as refused:
                    self.bridge.set_gradient_fill(stops, object_reference=reference)
                self.assertEqual(refused.exception.code, ErrorCode.INVALID_ARGUMENT)
                revised = self._step("revise gradient " + kind, lambda: self.bridge.set_gradient_fill(
                    stops, kind, angle_degrees=45., expected_fingerprint=inspected['fingerprint'], object_reference=reference))
                self.assertEqual(revised['before_fingerprint'], inspected['fingerprint']); records.append(revised)
            rgb_stops = [{'position_percent': position, 'color': {'model': 'rgb', 'red': r, 'green': g, 'blue': b}}
                         for position, (r, g, b) in ((0, (30, 90, 150)), (100, (200, 220, 255)))]
            title = self._step("gradient artistic title", lambda: self.bridge.add_text("Editable gradient title", 1, 8, 24, "Arial", True, "GradientTitle"))
            title_ref = self.bridge.get_object_info(object_name=title['object_name'])['object']['object_reference']
            paragraph = self._step("gradient paragraph", lambda: self.bridge.add_paragraph_text(
                "Editable paragraph gradient", 1, 9, 6, 1, size_points=16, object_name="GradientParagraph"))
            for reference in (title_ref, paragraph['object']['object_reference']):
                text = self.bridge.get_text_properties(object_reference=reference)['text']
                records.append(self._step("editable text gradient", lambda: self.bridge.set_gradient_fill(rgb_stops, object_reference=reference)))
                self.assertEqual(self.bridge.get_text_properties(object_reference=reference)['text'], text)
            (self.output_dir / "gradient-readback.json").write_text(json.dumps(records, indent=2), encoding='utf-8')
            self._step("save gradient fixture", lambda: self.bridge.save_document(str(self.output_dir / "gradients.cdr")))
            self._step("export gradient fixture", lambda: self.bridge.export_pdf_controlled(str(self.output_dir / "gradients.pdf")))
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed, failure)

    def test_powerclip_workflows_live(self) -> None:
        """Deferred editable mixed-payload clipping/extraction/rebuild gate."""
        from PIL import Image
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create clipping fixture",lambda:self.bridge.create_document(8.5,11))
            frame=self._step("closed clip frame",lambda:self.bridge.draw_rectangle(1,1,3,3,"ClipFrame"))
            frame_ref=self.bridge.get_object_info(object_name=frame["object_name"])["object"]["object_reference"]
            vector=self._step("editable clip vector",lambda:self.bridge.create_vector_path([
                {"start":{"x":0,"y":0},"closed":False,"segments":[
                    {"type":"cubic","control1":{"x":0,"y":2},"control2":{"x":4,"y":2},"end":{"x":4,"y":0}}]}],"ClipVector"))
            art_ref=vector["objects"][0]["object"]["object_reference"]
            title=self._step("editable clip title",lambda:self.bridge.add_text("Editable clip title",0,2,18,"Arial",True,"ClipTitle"))
            title_ref=self.bridge.get_object_info(object_name=title["object_name"])["object"]["object_reference"]
            raster_path=self.output_dir/"clipping-raster.png"
            Image.new("RGB",(600,300),(50,150,90)).save(raster_path,dpi=(300,300))
            imported=self._step("synthetic clipping bitmap",lambda:self.bridge.import_artwork(str(raster_path),"ClipBitmap"))
            photo_ref=self.bridge.get_object_info(object_name=imported["object_names"][0])["object"]["object_reference"]
            self._step("position clip bitmap",lambda:self.bridge.move_object(0,3,object_reference=photo_ref))
            source_snapshots=[self.bridge.get_powerclip(object_reference=reference)["powerclip"] for reference in (frame_ref,art_ref,title_ref,photo_ref)]
            created=self._step("create_powerclip mixed contain",lambda:self.bridge.create_powerclip(frame_ref,[photo_ref,title_ref,art_ref],
                fit_kind="contain",contents_locked=True,result_name="EditablePowerClip"))
            self.assertEqual(created["created_count"],1); self.assertTrue(created["source_preservation"]["verified"])
            clip_ref=created["objects"][0]["object"]["object_reference"]
            inspected=self._step("get_powerclip created",lambda:self.bridge.get_powerclip(object_reference=clip_ref))
            tree=inspected["powerclip"]["frame"]; self.assertEqual(len(tree["clip_children"]),1)
            payload=tree["clip_children"][0]; self.assertEqual(payload["shape_type_code"],7)
            self.assertEqual(sorted(node["shape_type_code"] for node in payload["group_children"]),[3,5,6])
            extracted=self._step("extract_powerclip_contents",lambda:self.bridge.extract_powerclip_contents(clip_ref,inspected["powerclip"]["fingerprint"],"EditableBody"))
            self.assertEqual(extracted["extracted_count"],1)
            extracted_ref=extracted["objects"][0]["object"]["object_reference"]
            group,_=self.bridge._resolve_object_reference(self.bridge.target_doc,extracted_ref,mutation=True)
            title_copies=[self.bridge._collection_item(group.Shapes,i) for i in range(1,group.Shapes.Count+1)
                          if self.bridge._collection_item(group.Shapes,i).Type==6]
            self.assertEqual(len(title_copies),1)
            copied_title_ref=self.bridge._reference_for_shape(self.bridge.target_doc,title_copies[0]); self.assertIsNotNone(copied_title_ref)
            self._step("edit extracted title",lambda:self.bridge.set_text_content("Revised clip title",object_reference=copied_title_ref))
            self.assertEqual(self.bridge.get_text_properties(object_reference=title_ref)["text"]["content"],"Editable clip title")
            self.assertEqual(self.bridge.get_powerclip(object_reference=clip_ref)["powerclip"],inspected["powerclip"])
            rebuilt=self._step("rebuild copied clip",lambda:self.bridge.create_powerclip(clip_ref,[extracted_ref],fit_kind="cover",
                replace_existing_contents=True,contents_locked=False,result_name="RevisedPowerClip"))
            self.assertFalse(rebuilt["objects"][0]["powerclip"]["frame"]["contents_locked"])
            self.assertEqual([self.bridge.get_powerclip(object_reference=reference)["powerclip"] for reference in (frame_ref,art_ref,title_ref,photo_ref)],source_snapshots)
            self._step("save clipping fixture",lambda:self.bridge.save_document(str(self.output_dir/"powerclip-workflows.cdr")))
            self._step("export clipping fixture",lambda:self.bridge.export_pdf_controlled(str(self.output_dir/"powerclip-workflows.pdf")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_document_inspection_live(self) -> None:
        """Consolidated inspection checks on a synthetic document with two pages."""
        passed=False; failure=None
        try:
            self._step("connect",self.bridge.connect)
            self.status=self._step("corel_status",self.bridge.status)
            self.assertTrue(self.status["connected"])
            self._step("create inspection fixture",lambda:self.bridge.create_document(8.5,11))
            self._step("inspection fixture text",lambda:self.bridge.add_text("INSPECT 001",1,2,12,"Arial",False,"InspectText"))
            document=self.bridge.target_doc
            with self.bridge._in_inches(document,strict_restore=True): document.AddPagesEx(1,3,4)
            self.bridge._collection_item(document.Pages,1).Activate()
            unit=document.Unit; reference_point=document.ReferencePoint
            page_before=self.bridge._reference_identity(document.ActivePage)
            info=self._step("get_document_info",self.bridge.get_document_info)
            self.assertEqual(info["document_name"],document.Name)
            pages=self._step("list_pages",self.bridge.list_pages)["pages"]
            self.assertEqual(len(pages),2)
            self.assertAlmostEqual(pages[1]["width_inches"],3,delta=.001)
            bounds=self._step("get_page_bounds",lambda:self.bridge.get_page_bounds(2))["bounds"]
            self.assertAlmostEqual(bounds["height"],4,delta=.001)
            layers=self._step("list_layers",lambda:self.bridge.list_layers(1))["layers"]
            self.assertTrue(layers)
            shape=self._step("get_object_info",lambda:self.bridge.get_object_info(object_name="InspectText"))["object"]
            self.assertEqual(shape["text"]["text"],"INSPECT 001")
            self.assertEqual(document.Unit,unit); self.assertEqual(document.ReferencePoint,reference_point)
            self.assertEqual(self.bridge._reference_identity(document.ActivePage),page_before)
            self._step("save inspection fixture",lambda:self.bridge.save_document(str(self.output_dir/"inspection-coverage.cdr")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_raster_print_workflow_live(self) -> None:
        """Consolidated raster placement gate with disposable generated artwork."""
        from PIL import Image
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            path=self.output_dir/"synthetic-raster.png"
            Image.new("RGB",(300,300),(40,120,200)).save(path,dpi=(300,300))
            result=self._step("prepare_print_job",lambda:self.bridge.prepare_print_job(str(path),1,1,3,2.5,
                copies=3,gutter_inches=0,minimum_dpi=150))
            self.assertEqual(result["created_count"],3); self.assertTrue(result["post_execution_verification"])
            self.assertFalse(result["print_ready"])
            self._step("save raster print fixture",lambda:self.bridge.save_document(str(self.output_dir/"raster-print.cdr")))
            self._step("export raster print fixture",lambda:self.bridge.export_pdf_controlled(str(self.output_dir/"raster-print.pdf")))
            baseline=self.bridge.app.Documents.Count
            with self.assertRaises(CorelBridgeError): self.bridge.prepare_print_job(str(path),1,1,3,2.5,copies=100)
            self.assertEqual(self.bridge.app.Documents.Count,baseline)
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_standalone_contour_nesting_live(self) -> None:
        """Consolidated low-level contour gate using a synthetic native L contour."""
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create contour fixture",lambda:self.bridge.create_document(12,18))
            self._step("create synthetic contour source",self._create_asymmetric_imposition_fixture)
            result=self._step("prepare_contour_nesting",lambda:self.bridge.prepare_contour_nesting(
                "Repeat_Unit","CutContour",12,18,copies=2,cutting_method="digital_cutter",allow_180_rotation=True))
            self.assertEqual(result["created_count"],2); self.assertTrue(result["source_preserved"])
            self.assertTrue(result["post_execution_verification"])
            self.assertEqual(self.bridge.target_doc.Pages.Count,2)
            self._step("save contour fixture",lambda:self.bridge.save_document(str(self.output_dir/"contour-coverage.cdr")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_controlled_pdf_live(self) -> None:
        """Deferred PDF gate on its own synthetic multipage document and output."""
        from corel_operator.pdf_inspection import inspect_pdf
        passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create PDF fixture",lambda:self.bridge.create_document(8.5,11))
            self._step("PDF fixture text",lambda:self.bridge.add_text("PDF 001",1,2,12,"Arial",False,"PdfText"))
            document=self.bridge.target_doc
            with self.bridge._in_inches(document,strict_restore=True): document.AddPagesEx(1,3,4)
            fields=('PublishRange ColorMode pdfVersion TextAsCurves EmbedFonts EmbedBaseFonts SubsetFonts IncludeBleed Bleed '
                'CropMarks RegistrationMarks DensitometerScales FileInformation EncryptType BitmapCompression DownsampleColor '
                'DownsampleGray DownsampleMono UseColorProfile ConvertSpotColors MaintainOPILinks EmbedFile ComplexFillsAsBitmaps '
                'TextExportMode TrueTypeToType1').split()
            original={field:getattr(document.PDFSettings,field) for field in fields}
            path=self.output_dir/"controlled-pdf.pdf"
            result=self._step("export_pdf_controlled",lambda:self.bridge.export_pdf_controlled(str(path)))
            self.assertTrue(result["inspection"]["checks_passed"])
            self.assertGreater(result["inspection"]["font_resource_count"],0)
            self.assertEqual(result["inspection"]["page_count"],2)
            self.assertEqual(original,{field:getattr(document.PDFSettings,field) for field in fields})
            inspection=self._step("inspect_pdf",lambda:inspect_pdf(str(path),2,[{"width":8.5,"height":11},{"width":3,"height":4}],True))
            with self.assertRaises(CorelBridgeError) as caught: self.bridge.export_pdf_controlled(str(path))
            self.assertEqual(caught.exception.code,ErrorCode.OUTPUT_EXISTS)
            self.assertEqual(inspection["source_sha256"],inspect_pdf(str(path))["source_sha256"])
            self._step("save PDF source fixture",lambda:self.bridge.save_document(str(self.output_dir/"controlled-pdf-source.cdr")))
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed(); self._write_report(passed,failure)

    def test_template_batch_live(self) -> None:
        """Deferred template gate using synthetic records and independently owned documents."""
        from corel_operator.template_jobs import read_template_csv,plan_template_batch
        source=None; output=None; passed=False; failure=None
        try:
            self.status=self._step("connect",self.bridge.connect)
            self._step("create synthetic template source",lambda:self.bridge.create_document(8.5,11))
            source=self.bridge.target_doc
            self._step("template background",lambda:self.bridge.draw_rectangle(1,1,3,2,"Background"))
            self._step("template name",lambda:self.bridge.add_text("NAME",1.2,2,12,"Arial",False,"Name"))
            self._step("template ID",lambda:self.bridge.add_text("ID",1.2,1.5,12,"Arial",False,"ID"))
            self._step("group template",lambda:self.bridge.group_shapes(["Background","Name","ID"],"Template"))
            self._step("save source",lambda:self.bridge.save_document(str(self.output_dir/"template-source.cdr")))
            manifest=self._step("inspect_text_template",lambda:self.bridge.inspect_text_template(object_name="Template"))["template"]
            csv_path=self.output_dir/"members.csv"
            csv_path.write_text("member,number\nAlia,001\nBilal,002\nCora,003\n",encoding="utf-8")
            rows=self._step("read_template_csv",lambda:read_template_csv(str(csv_path)))
            plan=self._step("plan_template_batch",lambda:plan_template_batch(manifest,{"member":"Name","number":"ID"},
                rows["records"],sheet_width_inches=6.5,sheet_height_inches=2.5,gutter_inches=0,record_key="number"))
            merged=self._step("execute_template_batch",lambda:self.bridge.execute_template_batch(plan,plan["fingerprint"]))
            output=self.bridge.target_doc
            self.assertIsNot(output,source); self.assertEqual(merged["item_count"],3); self.assertEqual(merged["sheet_count"],2)
            self.assertTrue(merged["source_preservation"]["verified"]); self.assertTrue(merged["fit_checks_passed"])
            for record in rows["records"]:
                matches=self._step("find output row "+record["number"],lambda:self.bridge.find_objects(text_contains=record["member"]))["matches"]
                self.assertEqual(len(matches),1)
            self._step("save merged editable output",lambda:self.bridge.save_document(str(self.output_dir/"template-output.cdr")))
            self._step("export merged PDF",lambda:self.bridge.export_pdf(str(self.output_dir/"template-output.pdf")))
            self._close_saved_target_if_needed(); output=None
            self.bridge._bind_target_document(source); source.Activate()
            self.assertEqual(self.bridge.inspect_text_template(object_reference=manifest["template_reference"])["template"]["fingerprint"],manifest["fingerprint"])
            bad_records=[{**rows["records"][0],"member":"X"*2000}]
            bad=plan_template_batch(manifest,{"member":"Name","number":"ID"},bad_records,
                sheet_width_inches=6.5,sheet_height_inches=2.5,gutter_inches=0)
            baseline={self.bridge._reference_identity(d) for d in self.bridge._open_document_proxies(self.bridge.app)}
            with self.assertRaises(CorelBridgeError): self.bridge.execute_template_batch(bad,bad["fingerprint"])
            self.assertEqual(baseline,{self.bridge._reference_identity(d) for d in self.bridge._open_document_proxies(self.bridge.app)})
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"; raise
        finally:
            self._close_saved_target_if_needed()
            if source is not None and any(self.bridge._same_com_object(source,d,strict=True) for d in self.bridge._open_document_proxies(self.bridge.app)):
                self.bridge._bind_target_document(source); source.Activate(); self._close_saved_target_if_needed()
            self._write_report(passed,failure)

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

    def test_imposition_orchestration_live(self) -> None:
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            self.assertEqual(self.status["version_major"], 17)
            created = self._step("create disposable imposition document", lambda: self.bridge.create_document(8.0, 6.0))
            self.assertTrue(created["created"])

            fixture = self._step("create asymmetric vector repeat", self._create_asymmetric_imposition_fixture)
            self.assertTrue(fixture["grouped"])
            self.assertEqual(fixture["group_name"], "Repeat_Unit")
            self.assertIn("CutContour", fixture["child_names"])

            inspection = self._step(
                "inspect_repeat_unit",
                lambda: self.bridge.inspect_repeat_unit(
                    "Repeat_Unit", "CutContour", "digital_cutter", True, 5,
                ),
            )
            self.assertTrue(inspection["ready"])
            self.assertEqual(inspection["workflow"], "contour_nesting")
            self.assertEqual(inspection["footprint_kind"], "contour")
            self.assertGreaterEqual(len(inspection["contour_points_inches"]), fixture["point_count"])
            source_before = inspection["source_identity"]

            planned = self._step(
                "prepare_imposition_job plan",
                lambda: self.bridge.prepare_imposition_job(
                    "Repeat_Unit",
                    "CutContour",
                    8.0,
                    6.0,
                    quantity=4,
                    margin_inches=0.0,
                    cutting_method="digital_cutter",
                    allow_180_rotation=True,
                ),
            )
            self.assertEqual(planned["status"], "planned")
            self.assertTrue(planned["ready_for_execution"])
            self.assertEqual(planned["plan"]["copies_per_sheet"], 4)
            self.assertEqual(planned["plan"]["layout_strategy"], "alternating_0_180_rows")
            self.assertTrue(planned["plan_fingerprint"].startswith("sha256:"))
            doc = self.bridge.target_doc
            self.assertIsNotNone(doc)
            self.assertEqual(int(doc.Pages.Count), 1)

            completed = self._step(
                "prepare_imposition_job execute",
                lambda: self.bridge.prepare_imposition_job(
                    "Repeat_Unit",
                    "CutContour",
                    8.0,
                    6.0,
                    quantity=4,
                    margin_inches=0.0,
                    cutting_method="digital_cutter",
                    allow_180_rotation=True,
                    confirm_execution=True,
                    approved_plan_fingerprint=planned["plan_fingerprint"],
                ),
            )
            self.assertEqual(completed["status"], "completed")
            self.assertTrue(completed["source_preserved"])
            execution = completed["execution"]
            self.assertTrue(execution["post_execution_verification"])
            self.assertEqual(execution["created_count"], 4)
            self.assertEqual(execution["output"]["page_index"], 2)
            self.assertEqual(execution["output"]["layer_name"], "Imposition_Repeats")
            self.assertEqual(execution["source_copy_method"], "clipboard_copy_paste")
            self.assertTrue(execution["clipboard_modified"])
            self.assertTrue(any("clipboard" in warning.lower() for warning in completed["warnings"]))
            self.assertEqual(
                [item["actual_rotation_degrees"] for item in execution["objects"]],
                [0.0, 0.0, 180.0, 180.0],
            )
            static_ids = [item["object"]["static_id"] for item in execution["objects"]]
            self.assertEqual(len(set(static_ids)), 4)
            self.assertEqual(int(doc.Pages.Count), 2)

            source_page = self.bridge._page_at(doc, 1)
            source_page.Activate()
            source_after = self._step(
                "verify source after successful imposition",
                lambda: self.bridge.inspect_repeat_unit(
                    "Repeat_Unit", "CutContour", "digital_cutter", True, 5,
                ),
            )
            self.assertEqual(source_after["source_identity"], source_before)

            rollback_plan = self._step(
                "prepare forced-rollback plan",
                lambda: self.bridge.prepare_imposition_job(
                    "Repeat_Unit",
                    "CutContour",
                    8.0,
                    6.0,
                    quantity=4,
                    margin_inches=0.0,
                    cutting_method="digital_cutter",
                    allow_180_rotation=True,
                    object_name_prefix="Rollback_Copy",
                ),
            )
            with patch("corel_operator.corel_bridge.contours_have_conflicts", return_value=True):
                with self.assertRaises(CorelBridgeError) as rollback_context:
                    self._step(
                        "forced imposition collision rollback",
                        lambda: self.bridge.prepare_imposition_job(
                            "Repeat_Unit",
                            "CutContour",
                            8.0,
                            6.0,
                            quantity=4,
                            margin_inches=0.0,
                            cutting_method="digital_cutter",
                            allow_180_rotation=True,
                            object_name_prefix="Rollback_Copy",
                            confirm_execution=True,
                            approved_plan_fingerprint=rollback_plan["plan_fingerprint"],
                        ),
                    )
            self.assertTrue(rollback_context.exception.details["rollback_attempted"])
            self.assertTrue(rollback_context.exception.details["rollback_verified"])
            self.assertTrue(rollback_context.exception.details["source_unchanged"])
            self.assertTrue(rollback_context.exception.details["clipboard_modified"])
            self.assertEqual(int(doc.Pages.Count), 2)
            self.assertEqual(int(self.bridge._page_at(doc, 2).Shapes.Count), 4)
            source_after_rollback = self._step(
                "verify source after imposition rollback",
                lambda: self.bridge.inspect_repeat_unit(
                    "Repeat_Unit", "CutContour", "digital_cutter", True, 5,
                ),
            )
            self.assertEqual(source_after_rollback["source_identity"], source_before)

            imposition_cdr = self.output_dir / "disposable-imposition.cdr"
            saved = self._step("save imposition artifact", lambda: self.bridge.save_document(str(imposition_cdr)))
            self.assertGreater(saved["bytes"], 0)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            report = self._write_report(passed, failure)
            print(f"Live imposition report: {report}")

    def test_find_objects_live(self) -> None:
        """Search only synthetic, disposable two-page artwork and retain readback."""
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            self._step("create_document", lambda: self.bridge.create_document(8.5, 11.0))
            doc = self.bridge.target_doc
            front = doc.ActivePage
            front_layer = front.CreateLayer("SearchArtwork")
            front_layer.Activate()

            self._step("create_nested_title", lambda: self.bridge.add_text(
                "Member Alice", 1.0, 2.0, 18, "Arial", False, "SearchTitle",
            ))
            self._step("create_inner_box", lambda: self.bridge.draw_rectangle(
                1.0, 3.0, 1.0, 1.0, "SearchInnerBox",
            ))
            self._step("group_inner", lambda: self.bridge.group_shapes(
                ["SearchTitle", "SearchInnerBox"], "SearchInner",
            ))
            self._step("create_outer_box", lambda: self.bridge.draw_rectangle(
                4.0, 3.0, 1.0, 1.0, "SearchOuterBox",
            ))
            self._step("group_outer", lambda: self.bridge.group_shapes(
                ["SearchInner", "SearchOuterBox"], "SearchOuter",
            ))
            # A group descendant and a new top-level object intentionally share a name.
            self._step("create_front_title", lambda: self.bridge.add_text(
                "Member Bob", 1.0, 5.0, 18, "Arial", False, "SearchTitle",
            ))

            with self.bridge._in_inches(doc):
                doc.AddPagesEx(1, 8.5, 11.0)
            back = self.bridge._page_at(doc, 2)
            back.Activate()
            back_layer = back.CreateLayer("SearchArtwork")
            back_layer.Activate()
            self._step("create_back_title", lambda: self.bridge.add_text(
                "Member Carol", 1.0, 2.0, 18, "Arial", False, "SearchTitle",
            ))
            self.bridge._find_shape(doc, "SearchTitle").CreateSelection()
            original_unit, original_reference, original_dirty = doc.Unit, doc.ReferencePoint, doc.Dirty
            original_selection = [
                int(self.bridge._collection_item(doc.SelectionRange, i).StaticID)
                for i in range(1, int(doc.SelectionRange.Count) + 1)
            ]

            all_matches = self._step("find_all_pages_nested_duplicates", lambda: self.bridge.find_objects(
                name_contains="searchtitle", layer_name="SearchArtwork",
            ))
            self.assertFalse(all_matches["truncated"])
            self.assertEqual(len(all_matches["matches"]), 3)
            self.assertEqual(sorted(m["group_depth"] for m in all_matches["matches"]), [0, 0, 2])
            self.assertEqual(sorted(m["page_index"] for m in all_matches["matches"]), [1, 1, 2])
            ids = [m["static_id"] for m in all_matches["matches"]]
            self.assertTrue(all(value is not None for value in ids))
            self.assertEqual(len(set(ids)), 3)
            self.assertEqual(all_matches, self.bridge.find_objects(
                name_contains="searchtitle", layer_name="SearchArtwork",
            ))

            scoped = self._step("find_page_layer_type_text", lambda: self.bridge.find_objects(
                name_contains="SearchTitle", shape_type_code=6, text_contains="alice",
                page_index=1, layer_name="SearchArtwork",
            ))
            self.assertEqual(len(scoped["matches"]), 1)
            self.assertEqual(scoped["matches"][0]["group_depth"], 2)
            top_level = self._step("find_top_level_only", lambda: self.bridge.find_objects(
                name_contains="SearchTitle", layer_name="SearchArtwork", include_nested=False,
            ))
            self.assertEqual(len(top_level["matches"]), 2)
            self.assertFalse(top_level["truncated"])
            limited = self._step("find_result_limit", lambda: self.bridge.find_objects(
                name_contains="SearchTitle", layer_name="SearchArtwork", max_results=1,
            ))
            self.assertEqual(limited["incomplete_reasons"], ["max_results"])
            depth_limited = self._step("find_depth_limit", lambda: self.bridge.find_objects(
                name_contains="SearchTitle", layer_name="SearchArtwork", max_depth=1,
            ))
            self.assertEqual(depth_limited["incomplete_reasons"], ["max_depth"])
            scan_limited = self._step("find_scan_limit", lambda: self.bridge.find_objects(max_scan=1))
            self.assertEqual(scan_limited["scanned_entries"], 1)
            self.assertEqual(scan_limited["incomplete_reasons"], ["max_scan"])

            self.assertTrue(self.bridge._same_com_object(doc.ActivePage, back))
            self.assertTrue(self.bridge._same_com_object(doc.ActivePage.ActiveLayer, back_layer))
            self.assertEqual((doc.Unit, doc.ReferencePoint, doc.Dirty), (original_unit, original_reference, original_dirty))
            selection = [
                int(self.bridge._collection_item(doc.SelectionRange, i).StaticID)
                for i in range(1, int(doc.SelectionRange.Count) + 1)
            ]
            self.assertEqual(selection, original_selection)

            readback_path = self.output_dir / "find-objects-readback.json"
            with readback_path.open("x", encoding="utf-8") as handle:
                json.dump({
                    "all_pages": all_matches, "scoped": scoped, "top_level": top_level,
                    "result_limit": limited, "depth_limit": depth_limited, "scan_limit": scan_limited,
                }, handle, indent=2)
                handle.write("\n")
            self._step("retain_search_readback", lambda: {"path": str(readback_path), "bytes": readback_path.stat().st_size})
            saved = self._step("save_disposable_search_document", lambda: self.bridge.save_document(
                str(self.output_dir / "disposable-object-search.cdr"),
            ))
            self.assertGreater(saved["bytes"], 0)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            self._write_report(passed, failure)

    def test_focused_object_inspection_live(self) -> None:
        """Read only synthetic fixtures and preserve selection, context and saved artwork."""
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            self._step("create_document", lambda: self.bridge.create_document(8.5, 11.0))
            doc = self.bridge.target_doc
            self._step("create_inspection_text", lambda: self.bridge.add_text(
                "Inspection text", 1.0, 5.0, 18, "Arial", True, "InspectionText",
            ))
            self._step("create_inspection_box", lambda: self.bridge.draw_rectangle(
                1.25, 2.5, 3.0, 0.5, "InspectionBox",
            ))
            self._step("apply_known_rgb_fill", lambda: self.bridge.set_fill_color(
                10, 20, 30, object_name="InspectionBox",
            ))
            box = self.bridge._find_shape(doc, "InspectionBox")
            box.CreateSelection()
            duplicate = box.Duplicate(0, 1)
            duplicate.Name = "InspectionBox"
            box_index = self.bridge._index_for_shape(doc, box)
            self.assertIsNotNone(box_index)
            doc.Unit = 3
            doc.ReferencePoint = 9
            self._step("save_synthetic_inspection_fixture", lambda: self.bridge.save_document(
                str(self.output_dir / "disposable-focused-inspection.cdr"),
            ))

            def state():
                return {
                    "unit": int(doc.Unit), "reference_point": int(doc.ReferencePoint),
                    "dirty": bool(doc.Dirty), "count": int(doc.ActivePage.Shapes.Count),
                    "page": self.bridge._com_identity(doc.ActivePage),
                    "layer": self.bridge._com_identity(doc.ActivePage.ActiveLayer),
                    "selection": [
                        int(self.bridge._collection_item(doc.SelectionRange, i).StaticID)
                        for i in range(1, int(doc.SelectionRange.Count) + 1)
                    ],
                }

            before = state()
            self.assertFalse(before["dirty"])
            bounds = self._step("inspect_box_bounds", lambda: self.bridge.get_object_bounds(
                shape_index=box_index,
            ))
            self.assertEqual(bounds["unit"], "inch")
            for actual, expected in (
                (bounds["bounds"]["lower_left"]["x"], 1.25),
                (bounds["bounds"]["lower_left"]["y"], 2.5),
                (bounds["bounds"]["width"], 3.0), (bounds["bounds"]["height"], 0.5),
            ):
                self.assertAlmostEqual(actual, expected, delta=0.01)
            text = self._step("inspect_text_properties", lambda: self.bridge.get_text_properties(
                object_name="InspectionText",
            ))
            self.assertEqual(text["text"]["content"], "Inspection text")
            self.assertEqual(text["text"]["font"], "Arial")
            self.assertAlmostEqual(text["text"]["size_points"], 18, delta=0.1)
            self.assertTrue(text["text"]["bold"])
            short = self._step("inspect_bounded_text", lambda: self.bridge.get_text_properties(
                object_name="InspectionText", max_text_chars=4,
            ))
            self.assertEqual(short["text"]["content"], "Insp")
            self.assertTrue(short["text"]["content_truncated"])
            fill = self._step("inspect_native_fill", lambda: self.bridge.get_fill(shape_index=box_index))
            self.assertEqual(fill["fill"]["type"], "uniform")
            self.assertEqual(fill["fill"]["color"]["model"], "rgb")
            self.assertEqual(fill["fill"]["color"]["value"], {"red": 10, "green": 20, "blue": 30})
            self.assertEqual(bounds["object"], fill["object"])
            for method, arguments, expected in (
                ("get_object_bounds", {"object_name": "InspectionBox"}, ErrorCode.AMBIGUOUS_SELECTOR),
                ("get_fill", {"object_name": "InspectionBox"}, ErrorCode.AMBIGUOUS_SELECTOR),
                ("get_text_properties", {"shape_index": box_index}, ErrorCode.INVALID_ARGUMENT),
                ("get_fill", {"object_name": "MissingInspectionObject"}, ErrorCode.OBJECT_NOT_FOUND),
            ):
                with self.assertRaises(CorelBridgeError) as caught:
                    getattr(self.bridge, method)(**arguments)
                self.assertEqual(caught.exception.code, expected)
            self.assertEqual(state(), before)
            readback_path = self.output_dir / "focused-inspection-readback.json"
            with readback_path.open("x", encoding="utf-8") as handle:
                json.dump({"bounds": bounds, "text": text, "short_text": short, "fill": fill},
                          handle, indent=2, allow_nan=False)
                handle.write("\n")
            self._step("retain_focused_readback", lambda: {
                "path": str(readback_path), "bytes": readback_path.stat().st_size,
            })
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            self._write_report(passed, failure)

    def test_closed_document_guard_live(self) -> None:
        """Close one owned fixture and prove an edit cannot reach the other one."""
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            self._step("create_first_fixture", lambda: self.bridge.create_document(8.5, 11.0))
            first = self.bridge.target_doc
            self._step("save_first_fixture", lambda: self.bridge.save_document(
                str(self.output_dir / "closed-target.cdr"),
            ))
            self._step("create_second_fixture", lambda: self.bridge.create_document(8.5, 11.0))
            second = self.bridge.target_doc
            self._step("save_second_fixture", lambda: self.bridge.save_document(
                str(self.output_dir / "remaining-target.cdr"),
            ))
            self.bridge._bind_target_document(first)
            first.Close()
            with self.assertRaises(CorelBridgeError) as caught:
                self.bridge.move_object(1, 2, object_name="MissingSyntheticShape")
            self.assertEqual(caught.exception.code, ErrorCode.NO_TARGET_DOCUMENT)
            self.assertIsNone(self.bridge.target_doc)
            self.assertTrue(self.bridge._same_com_object(self.bridge.app.ActiveDocument, second))
            self.assertEqual(int(second.ActivePage.Shapes.Count), 0)
            self.assertFalse(second.Dirty)
            self._step("verify_closed_target_refusal", lambda: {
                "error_code": caught.exception.code.value, "remaining_document_unchanged": True,
            })
            self.bridge._bind_target_document(second)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            self._write_report(passed, failure)

    def test_object_references_live(self) -> None:
        """Consolidated ID-001 gate using synthetic artwork and its own saved file only."""
        passed = False
        failure: str | None = None
        try:
            self.status = self._step("connect / corel_status", self.bridge.connect)
            self._step("create_reference_fixture", lambda: self.bridge.create_document(8.5, 11.0))
            self.bridge.add_text("Nested title", 1, 2, object_name="ReferenceTitle")
            self.bridge.draw_rectangle(1, 3, 1, 1, object_name="ReferenceBox")
            self.bridge.group_shapes(["ReferenceTitle", "ReferenceBox"], "ReferenceGroup")
            self.bridge.add_text("Top title", 1, 5, object_name="ReferenceTitle")
            doc = self.bridge.target_doc
            nested_match = self.bridge.find_objects(text_contains="Nested title")["matches"][0]
            reference = nested_match["object_reference"]
            self.assertIsNotNone(reference)
            self.assertEqual(nested_match["group_depth"], 1)
            self.assertEqual(self.bridge.get_text_properties(object_reference=reference)["text"]["content"], "Nested title")
            self.assertEqual(reference, self.bridge.find_objects(text_contains="Nested title")["matches"][0]["object_reference"])

            # X7 ShapeRange.OrderToFront is documented; native proxy/ID behavior is measured here.
            shape_range = self.bridge.app.CreateShapeRange()
            shape_range.Add(self.bridge._find_shape(doc, object_name="ReferenceGroup"))
            shape_range.OrderToFront()
            self._step("reference_survives_stacking_reorder", lambda: self.bridge.get_text_properties(object_reference=reference))
            self.bridge.set_text_content("Nested changed", object_reference=reference)
            self.assertEqual(self.bridge.get_text_properties(object_name="ReferenceTitle")["text"]["content"], "Top title")
            fresh = self.bridge.rename_object("NestedRenamed", object_reference=reference)["object"]["object_reference"]
            self.assertIsNotNone(fresh)
            with self.assertRaises(CorelBridgeError) as stale_name:
                self.bridge.set_text_content("Forbidden", object_reference=reference)
            self.assertEqual(stale_name.exception.code, ErrorCode.OBJECT_NOT_FOUND)
            duplicate = self.bridge.duplicate_object(object_reference=fresh, new_name="NestedCopy")
            duplicate_ref = duplicate["object"]["object_reference"]
            self.assertIsNotNone(duplicate_ref)
            self.assertNotEqual(duplicate_ref["shape_identity"], fresh["shape_identity"])
            self.assertEqual(self.bridge.get_text_properties(object_reference=duplicate_ref)["text"]["content"], "Nested changed")
            self.bridge._resolve_object_reference(doc, duplicate_ref)[0].Delete()
            with self.assertRaises(CorelBridgeError) as deleted:
                self.bridge.move_object(6, 7, object_reference=duplicate_ref)
            self.assertEqual(deleted.exception.code, ErrorCode.OBJECT_NOT_FOUND)

            self._step("save_reference_fixture", lambda: self.bridge.save_document(str(self.cdr_path)))
            before_reopen_id = fresh["static_id"]
            doc.Close()
            with self.assertRaises(CorelBridgeError) as closed:
                self.bridge.get_text_properties(object_reference=fresh)
            self.assertEqual(closed.exception.code, ErrorCode.NO_TARGET_DOCUMENT)
            # Open only the file this gate just created; bind as a new document lifetime.
            reopened = self.bridge.app.OpenDocument(str(self.cdr_path))
            self.bridge._bind_target_document(reopened, new_document=True)
            with self.assertRaises(CorelBridgeError) as old_session:
                self.bridge.set_text_content("Forbidden", object_reference=fresh)
            self.assertEqual(old_session.exception.code, ErrorCode.OBJECT_NOT_FOUND)
            reopened_match = self.bridge.find_objects(name_contains="NestedRenamed")["matches"][0]
            reopened_ref = reopened_match["object_reference"]
            self.assertIsNotNone(reopened_ref)
            self.assertEqual(self.bridge.get_text_properties(object_reference=reopened_ref)["text"]["content"], "Nested changed")
            restarted = CorelBridge()
            restarted.app = self.bridge.app
            restarted._bind_target_document(reopened)
            with self.assertRaises(CorelBridgeError) as restart:
                restarted.move_object(6, 7, object_reference=reopened_ref)
            self.assertEqual(restart.exception.code, ErrorCode.OBJECT_NOT_FOUND)
            readback = {
                "before_reopen_static_id": before_reopen_id,
                "after_reopen_static_id": reopened_match["static_id"],
                "reorder_reference": reference, "reopened_reference": reopened_ref,
                "closed_document_error": closed.exception.code.value,
                "reopened_session_error": old_session.exception.code.value,
                "bridge_restart_error": restart.exception.code.value,
            }
            (self.output_dir / "reference-readback.json").write_text(json.dumps(readback, indent=2), encoding="utf-8")
            self._step("verify_reference_lifecycle", lambda: {"updated": True, "object_count": len(self.bridge.find_objects()["matches"])})
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._close_saved_target_if_needed()
            self._write_report(passed, failure)

    def test_layout_transforms_live(self) -> None:
        """X7 matrices/pivots/mirrors/sibling order/distribution on owned shapes."""
        passed,failure,owned_session=False,None,None
        try:
            self.status=self._step("connect layout fixture",self.bridge.connect)
            self._step("create layout document",lambda:self.bridge.create_document(8.5,11))
            document=self.bridge.target_doc
            owned_session=self.bridge._document_session_id(document)
            original_context=(int(document.Unit),int(document.ReferencePoint))
            for name,x,width,height in (("LayoutA",1,2,1),("LayoutB",4,1,2),("LayoutC",7,3,1)):
                self.bridge.draw_rectangle(x,1,width,height,object_name=name)
            references=[self.bridge.get_object_transform(object_name=name)["object"]["object_reference"]
                        for name in ("LayoutA","LayoutB","LayoutC")]
            self.assertTrue(all(reference is not None for reference in references))
            rotated=self._step("rotate native asymmetric shape",lambda:self.bridge.rotate_object(90,object_reference=references[0]))
            bounds=rotated["actual_transform"]["bounds_inches"]
            self.assertAlmostEqual(bounds["width"],1,delta=.01)
            self.assertAlmostEqual(bounds["height"],2,delta=.01)
            self.assertAlmostEqual(bounds["x"]+bounds["width"]/2,2,delta=.01)
            self.assertAlmostEqual(bounds["y"]+bounds["height"]/2,1.5,delta=.01)
            pivoted=self._step("rotate native external pivot",lambda:self.bridge.rotate_object(
                180,relative=False,center_x_inches=0,center_y_inches=0,object_reference=references[0]))
            self.assertAlmostEqual(pivoted["actual_transform"]["rotation_degrees"],180,delta=.001)
            self.bridge.rotate_object(-90,center_x_inches=0,center_y_inches=0,object_reference=references[0])
            self.bridge.rotate_object(0,relative=False,object_reference=references[0])
            self.bridge.move_object(1,1,object_reference=references[0])
            before=self.bridge.get_object_transform(object_reference=references[1])["transform"]
            mirrors=[]
            for axis in ("horizontal","vertical","both"):
                mirrors.append(self._step(f"mirror native {axis}",lambda axis=axis:self.bridge.flip_object(axis,object_reference=references[1])))
                mirrored=mirrors[-1]["actual_transform"]
                self.assertAlmostEqual(mirrored["matrix"][0],before["matrix"][0]*(-1 if axis in ("horizontal","both") else 1),delta=.0001)
                self.assertAlmostEqual(mirrored["matrix"][3],before["matrix"][3]*(-1 if axis in ("vertical","both") else 1),delta=.0001)
                for field in ("x","y","width","height"):
                    self.assertAlmostEqual(mirrored["bounds_inches"][field],before["bounds_inches"][field],delta=.001)
                self.bridge.flip_object(axis,object_reference=references[1])
            after=self.bridge.get_object_transform(object_reference=references[1])["transform"]
            for actual,expected in zip(after["matrix"],before["matrix"]):
                self.assertAlmostEqual(actual,expected,delta=.0001)
            order=[]
            for position in ("front","back_one","forward_one","back"):
                order.append(self._step(f"native stacking {position}",lambda position=position:self.bridge.order_object(position,object_reference=references[2])))
            gaps=self._step("native equal-gap distribution",lambda:self.bridge.distribute_objects("horizontal",object_references=references))
            self.assertAlmostEqual(gaps["spacing_inches"],1.5,delta=.01)
            explicit=self._step("native explicit-gap distribution",lambda:self.bridge.distribute_objects(
                "horizontal",object_references=references,spacing_inches=.25))
            for previous,current in zip(explicit["objects"],explicit["objects"][1:]):
                left=previous["actual_transform"]["bounds_inches"]
                right=current["actual_transform"]["bounds_inches"]
                self.assertAlmostEqual(right["x"]-left["x"]-left["width"],.25,delta=.001)
            for reference,y in zip(references,(1,4,7)):
                x=self.bridge.get_object_transform(object_reference=reference)["transform"]["bounds_inches"]["x"]
                self.bridge.move_object(x,y,object_reference=reference)
            centers=self._step("native equal-center distribution",lambda:self.bridge.distribute_objects(
                "vertical",object_references=references,mode="equal_centers"))
            center_values=[item["actual_transform"]["bounds_inches"]["y"]+item["actual_transform"]["bounds_inches"]["height"]/2 for item in centers["objects"]]
            self.assertAlmostEqual(center_values[1]-center_values[0],center_values[2]-center_values[1],delta=.001)
            self.bridge.group_shapes(["LayoutA","LayoutB"],group_name="LayoutGroup")
            matches={m["object_name"]:m["object_reference"] for m in self.bridge.find_objects()["matches"]}
            nested_order=self._step("native nested sibling order",lambda:self.bridge.order_object("front",object_reference=matches["LayoutB"]))
            self.assertEqual(nested_order["actual_order"]["sibling_count"],2)
            with self.assertRaises(CorelBridgeError) as ancestor:
                self.bridge.distribute_objects("horizontal",object_references=[matches["LayoutGroup"],matches["LayoutA"],matches["LayoutC"]])
            self.assertEqual(ancestor.exception.code,ErrorCode.INVALID_ARGUMENT)
            self.assertEqual((int(document.Unit),int(document.ReferencePoint)),original_context)
            (self.output_dir/"layout-readback.json").write_text(json.dumps({"rotated":rotated,"pivoted":pivoted,
                "mirrors":mirrors,"orders":order,"gaps":gaps,"explicit":explicit,"centers":centers,"nested_order":nested_order},indent=2),encoding="utf-8")
            passed=True
        except BaseException as exc:
            failure=f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                if owned_session is not None and self.bridge.target_doc is not None:
                    document=self.bridge._target_document()
                    if self.bridge._document_session_id(document)!=owned_session:
                        raise AssertionError("Refusing layout cleanup of an unowned target")
                    self._step("save owned layout fixture",lambda:self.bridge.save_document(str(self.cdr_path)))
                    document.Close()
                    self.bridge._invalidate_target_document()
            except BaseException as exc:
                passed=False
                failure=f"Layout cleanup failed: {type(exc).__name__}: {exc}"
                raise
            finally:
                self._write_report(passed,failure)

    def test_typography_live(self) -> None:
        """Native typography/readback on owned synthetic artwork; never run by default."""
        passed, failure, owned_session = False, None, None
        try:
            self.status = self._step("connect typography fixture", self.bridge.connect)
            self._step("create typography document", lambda: self.bridge.create_document(8.5, 11))
            document = self.bridge.target_doc
            owned_session = self.bridge._document_session_id(document)
            original_context = (int(document.Unit), int(document.ReferencePoint))
            fonts = self._step("inspect native Arial catalog", lambda: self.bridge.list_fonts("Arial", max_scan=10000))
            self.assertFalse(fonts["truncated"])
            self.assertIn("Arial", fonts["fonts"])
            self.bridge.add_text("Editable title", 1, 8, object_name="TypeTitle")
            title = self.bridge.get_text_properties(object_name="TypeTitle")
            reference = title["object"]["object_reference"]
            self.assertIsNotNone(reference)
            changed = self._step("revise native title typography", lambda: self.bridge.set_text_style(
                font="Arial", size_points=28, bold=True, italic=True, underline="single",
                alignment="center", object_reference=reference))
            self.assertEqual(changed["actual_style"]["size_points"], 28)
            self.assertTrue(changed["actual_style"]["bold"])
            self.assertEqual(self.bridge.get_text_properties(object_reference=reference)["text"]["content"], "Editable title")
            body_text = "Synthetic paragraph\n" + "Overflow measurement example. " * 100
            paragraph = self._step("create native paragraph frame", lambda: self.bridge.add_paragraph_text(
                body_text, 1, 4, 2, .5, size_points=24, object_name="TypeBody"))
            body_reference = paragraph["object"]["object_reference"]
            self.assertIsNotNone(body_reference)
            self.assertEqual(paragraph["layout"]["text_type"], "paragraph")
            self.assertEqual(paragraph["layout"]["frame_count"], 1)
            self.assertTrue(paragraph["layout"]["overflow"])
            self.assertEqual(paragraph["layout"]["overflow_scope"], "linked_story")
            for field, expected in (("x", 1), ("y", 4), ("width", 2), ("height", .5)):
                self.assertAlmostEqual(paragraph["actual_bounds_inches"][field], expected, delta=.02)
            styled_body = self._step("revise paragraph font size", lambda: self.bridge.set_text_style(
                size_points=12, alignment="justify", object_reference=body_reference))
            self.assertEqual(styled_body["actual_style"]["alignment"], "justify")
            body = self.bridge.get_text_properties(object_reference=body_reference, max_text_chars=10000)
            normalize = lambda value: value.replace("\r\n", "\r").replace("\n", "\r")
            self.assertEqual(normalize(body["text"]["content"]), normalize(body_text))
            self._step("set native text color", lambda: self.bridge.set_fill_color(20, 40, 60, object_reference=body_reference))
            self.assertEqual(self.bridge.get_fill(object_reference=body_reference)["fill"]["type"], "uniform")
            shape_count = int(document.ActivePage.Shapes.Count)
            with self.assertRaises(CorelBridgeError) as missing:
                self.bridge.set_text_style(font="SyntheticMissingFont_941923", object_reference=body_reference)
            self.assertEqual(missing.exception.code, ErrorCode.INVALID_ARGUMENT)
            self.assertEqual(int(document.ActivePage.Shapes.Count), shape_count)
            self.assertEqual((int(document.Unit), int(document.ReferencePoint)), original_context)
            (self.output_dir / "typography-readback.json").write_text(
                json.dumps({"title": changed, "paragraph": paragraph, "revised_body": styled_body,
                            "body_inspection": body}, indent=2, ensure_ascii=False), encoding="utf-8")
            self._step("verify native typography", lambda: {"updated": True})
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                if owned_session is not None and self.bridge.target_doc is not None:
                    document = self.bridge._target_document()
                    if self.bridge._document_session_id(document) != owned_session:
                        raise AssertionError("Refusing typography cleanup of an unowned target")
                    self._step("save owned typography fixture", lambda: self.bridge.save_document(str(self.cdr_path)))
                    document.Close()
                    self.bridge._invalidate_target_document()
            except BaseException as exc:
                passed = False
                failure = f"Typography cleanup failed: {type(exc).__name__}: {exc}"
                raise
            finally:
                self._write_report(passed, failure)

    def test_worker_recovery_live(self) -> None:
        """Native synthetic edits with a controlled caller timeout; real modal behavior is separate."""
        from corel_operator import server
        from corel_operator.operation_records import OperationJournal

        released = threading.Event()
        journal = OperationJournal(self.output_dir / "operation-records")
        dispatcher = None
        passed = False
        failure: str | None = None

        class RecoveryFixtureBridge(CorelBridge):
            def create_document(inner, *args, **kwargs):
                result = super(RecoveryFixtureBridge, inner).create_document(*args, **kwargs)
                inner._owned_session = inner._document_session_id(inner.target_doc)
                return result

            def add_text(inner, *args, **kwargs):
                result = super(RecoveryFixtureBridge, inner).add_text(*args, **kwargs)
                if not released.wait(timeout=3):
                    raise CorelBridgeError("Synthetic post-edit barrier was not released.", ErrorCode.COREL_COM_ERROR)
                return result

            def set_text_content(inner, new_text, *args, **kwargs):
                result = super(RecoveryFixtureBridge, inner).set_text_content(new_text, *args, **kwargs)
                if new_text == "Injected partial update":
                    raise CorelBridgeError("Synthetic failure after a native text edit.", ErrorCode.COREL_COM_ERROR)
                return result

            def close_owned_fixture(inner, checkpoint):
                if inner.target_doc is None:
                    return {"closed": True}
                document = inner._target_document()
                if inner._document_session_id(document) != inner._owned_session:
                    raise AssertionError("Refusing to close an unowned target")
                if document.Dirty:
                    inner.save_document(checkpoint)
                document.Close()
                inner._invalidate_target_document()
                return {"closed": True}

        try:
            with patch.object(server, "CorelBridge", RecoveryFixtureBridge):
                dispatcher = server.CorelDispatcher()
            with patch.object(server, "dispatcher", dispatcher), patch.object(server, "operation_journal", journal):
                self.status = self._step("connect recovery fixture", server.corel_status)["data"]
                self.assertTrue(self.status["connected"])
                created = self._step("create owned recovery document", lambda: server.create_document(8.5, 11))
                self.assertTrue(created["ok"])
                dispatcher.call_timeout_seconds = 0.05
                timed_out = server.add_text("Recovery secret text", 1, 2, object_name="RecoveryTitle")
                self.assertEqual(timed_out["error"]["code"], "OPERATION_TIMEOUT")
                operation_id = timed_out["operation_id"]
                state = server.get_operator_state()["data"]
                self.assertEqual(state["state"], "timed_out_but_running")
                self.assertTrue(state["recovery_required"])
                self.assertEqual(server.draw_rectangle(1, 3, 1, 1)["error"]["code"], "WORKER_BUSY")
                released.set()
                deadline = time.monotonic() + 10
                while dispatcher.snapshot()["active_operation"] is not None:
                    if time.monotonic() >= deadline:
                        raise AssertionError("Synthetic native worker did not complete")
                    time.sleep(0.01)
                dispatcher.call_timeout_seconds = 120
                status = server.get_operation_status(operation_id)["data"]
                self.assertEqual(status["status"], "completed")
                self.assertEqual(server.draw_rectangle(1, 3, 1, 1)["error"]["code"], "RECOVERY_REQUIRED")
                self.assertEqual(server.get_text_properties(object_name="RecoveryTitle")["data"]["text"]["content"], "Recovery secret text")
                recovered = server.reconcile_operator_state(operation_id)
                self.assertTrue(recovered["ok"])
                self.assertEqual(recovered["data"]["document_state"]["page_object_count"], 1)
                partial = server.set_text_content("Injected partial update", object_name="RecoveryTitle")
                self.assertEqual(partial["error"]["code"], "COREL_COM_ERROR")
                partial_id = server.get_operator_state()["data"]["recovery"]["operation_id"]
                self.assertEqual(server.reconcile_operator_state(partial_id)["error"]["code"], "CONFIRMATION_REQUIRED")
                self.assertEqual(server.get_text_properties(object_name="RecoveryTitle")["data"]["text"]["content"], "Injected partial update")
                self.assertTrue(server.reconcile_operator_state(partial_id, acknowledge_partial_changes=True)["ok"])
                self.assertTrue(server.get_operator_state()["data"]["accepting_mutations"])
                saved = self._step("save recovered native fixture", lambda: server.save_document(str(self.cdr_path)))
                self.assertTrue(saved["ok"])
                readback = {"late_operation": status, "reconciliation": recovered["data"], "partial_operation_id": partial_id}
                (self.output_dir / "worker-recovery-readback.json").write_text(json.dumps(readback, indent=2), encoding="utf-8")
                for path in (self.output_dir / "operation-records").glob("*.jsonl"):
                    contents = path.read_text(encoding="utf-8")
                    self.assertNotIn("Recovery secret text", contents)
                    self.assertNotIn("Injected partial update", contents)
            passed = True
        except BaseException as exc:
            failure = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            released.set()
            original_failure = failure is not None
            cleanup_failed = False
            if dispatcher is not None:
                dispatcher.call_timeout_seconds = 120
                try:
                    dispatcher.call("close_owned_fixture", str(self.output_dir / "recovery-cleanup.cdr"))
                except Exception as exc:
                    cleanup_failed = True
                    self.cleanup_notes.append(f"Recovery fixture cleanup: {type(exc).__name__}")
                try:
                    dispatcher.close()
                except RuntimeError:
                    cleanup_failed = True
                    self.cleanup_notes.append("Recovery worker shutdown remains incomplete")
            journal.close()
            if cleanup_failed:
                passed = False
                failure = failure or "Recovery fixture cleanup did not complete."
            self._write_report(passed, failure)
            if cleanup_failed and not original_failure:
                raise AssertionError("Recovery fixture cleanup did not complete.")

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
