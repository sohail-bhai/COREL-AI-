from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from corel_operator.phase2_validation import (
    Phase2ValidationError,
    validate_phase2_workspace,
)


TEMP_ROOT = Path(tempfile.gettempdir()) / "opencode"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class Phase2ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _artwork(
        pattern: str,
        size: tuple[int, int] = (297, 210),
        plaque_bounds: tuple[int, int] = (65, 150),
    ) -> Image.Image:
        image = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 286, 199), fill=(180, 170, 160))
        draw.rectangle((10, plaque_bounds[0], 286, plaque_bounds[1]), fill=(20, 20, 20))
        if pattern == "vertical":
            for x in range(20, 287, 20):
                draw.line((x, 14, x, 59), fill=(45, 45, 45), width=2)
                draw.line((x, 156, x, 195), fill=(45, 45, 45), width=2)
        elif pattern == "horizontal":
            for y in range(18, 60, 10):
                draw.line((15, y, 282, y), fill=(45, 45, 45), width=2)
            for y in range(160, 196, 10):
                draw.line((15, y, 282, y), fill=(45, 45, 45), width=2)
        else:
            raise ValueError(f"Unknown synthetic pattern: {pattern}")
        return image

    def _write_workspace(
        self,
        *,
        reference_pattern: str = "vertical",
        preview_pattern: str = "vertical",
        preview_size: tuple[int, int] = (297, 210),
        preview_plaque_bounds: tuple[int, int] = (65, 150),
    ) -> None:
        reference_dir = self.workspace / "00_reference_nonprinting"
        reference_dir.mkdir()
        source = reference_dir / "source_original.jpeg"
        source.write_bytes(b"retained-source")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

        reference = self._artwork(reference_pattern)
        preview = self._artwork(preview_pattern, preview_size, preview_plaque_bounds)
        reference.save(reference_dir / "reference_rectified_a4.png")
        preview.save(self.workspace / "phase2_structure_preview.png")
        preview.save(self.workspace / "phase2_structure_overlay_analysis.png")
        preview.save(self.workspace / "phase2_structure_difference_analysis.png")

        measurements = {
            "source_preflight": {"sha256": source_hash},
            "rectified_image": {"width_pixels": 297, "height_pixels": 210},
            "inner_printed_field": {
                "average_bounds_mm": {
                    "left": 10.0,
                    "top": 200.0,
                    "right": 287.0,
                    "bottom": 10.0,
                }
            },
        }
        manifest = {"source_copy": {"sha256": source_hash}, "status": "PHASE_1_RECTIFIED_AND_CALIBRATED"}
        audit = {
            "result": "PASS_PHASE2_STRUCTURE",
            "source_sha256": source_hash,
            "document_audit": {
                "reference_layer_gate": {"passed": True},
                "contains_no_printable_bitmaps": True,
                "powerclip_verified": True,
                "all_printable_top_level_bounds_within_page": True,
            },
            "pdf_audit": {"embedded_image_objects": 0},
        }
        (self.workspace / "v2_measurements.json").write_text(json.dumps(measurements), encoding="utf-8")
        (self.workspace / "V2_WORKSPACE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.workspace / "phase2_structure_audit.json").write_text(json.dumps(audit), encoding="utf-8")
        (self.workspace / "Alhamdulillah_A4_Landscape_V2_Phase2_Structure.cdr").write_bytes(b"cdr")
        (self.workspace / "Alhamdulillah_A4_Landscape_V2_Phase2_Structure.pdf").write_bytes(b"pdf")

    def test_matching_geometry_passes_the_independent_gate(self) -> None:
        self._write_workspace()

        report = validate_phase2_workspace(self.workspace)

        self.assertEqual(report["result"], "PASS_PHASE2_GATE")
        self.assertTrue(report["field_geometry"]["passed"])
        self.assertTrue(report["plaque_geometry"]["passed"])
        self.assertTrue(report["trellis_geometry"]["passed"])
        self.assertEqual(report["blockers"], [])

    def test_trellis_mismatch_blocks_a_structurally_valid_workspace(self) -> None:
        self._write_workspace(preview_pattern="horizontal")

        report = validate_phase2_workspace(self.workspace)

        self.assertEqual(report["result"], "FAIL_PHASE2_GATE")
        self.assertTrue(report["checks"]["vector_integrity_build_audit"])
        self.assertTrue(report["checks"]["plaque_geometry"])
        self.assertFalse(report["checks"]["trellis_geometry"])
        self.assertIn("trellis_geometry", report["blockers"])

    def test_plaque_mismatch_blocks_a_structurally_valid_workspace(self) -> None:
        self._write_workspace(preview_plaque_bounds=(75, 140))

        report = validate_phase2_workspace(self.workspace)

        self.assertTrue(report["checks"]["vector_integrity_build_audit"])
        self.assertFalse(report["checks"]["plaque_geometry"])
        self.assertIn("plaque_geometry", report["blockers"])

    def test_source_identity_mismatch_blocks_the_gate(self) -> None:
        self._write_workspace()
        source = self.workspace / "00_reference_nonprinting" / "source_original.jpeg"
        source.write_bytes(b"changed-after-preparation")

        report = validate_phase2_workspace(self.workspace)

        self.assertFalse(report["checks"]["source_identity"])
        self.assertIn("source_identity", report["blockers"])

    def test_missing_retained_artifact_fails_closed(self) -> None:
        self._write_workspace()
        (self.workspace / "phase2_structure_overlay_analysis.png").unlink()

        with self.assertRaisesRegex(Phase2ValidationError, "overlay"):
            validate_phase2_workspace(self.workspace)

    def test_dimension_mismatch_is_reported_without_comparing_unaligned_images(self) -> None:
        self._write_workspace(preview_size=(300, 210))

        report = validate_phase2_workspace(self.workspace)

        self.assertEqual(report["result"], "FAIL_PHASE2_GATE")
        self.assertFalse(report["checks"]["image_dimensions"])
        self.assertIn("image_dimensions", report["blockers"])
        self.assertFalse(report["field_geometry"]["evaluated"])
        self.assertFalse(report["plaque_geometry"]["evaluated"])
        self.assertFalse(report["trellis_geometry"]["evaluated"])

    def test_incomplete_structure_audit_is_a_blocker_not_a_key_error(self) -> None:
        self._write_workspace()
        audit_path = self.workspace / "phase2_structure_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        del audit["document_audit"]
        audit_path.write_text(json.dumps(audit), encoding="utf-8")

        report = validate_phase2_workspace(self.workspace)

        self.assertFalse(report["checks"]["vector_integrity_build_audit"])
        self.assertIn("vector_integrity_build_audit", report["blockers"])


if __name__ == "__main__":
    unittest.main()
