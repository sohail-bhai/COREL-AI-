from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from corel_operator.reference_recreation import (
    CORNER_NAMES,
    ReferencePreparationError,
    apply_projective_transform,
    calibrate_a4_landscape,
    inspect_reference_image,
    measure_inner_printed_field,
    prepare_a4_reference_workspace,
    rectify_a4_reference,
    save_rotated_reference,
    validate_page_corners,
)


TEMP_ROOT = Path(tempfile.gettempdir()) / "opencode"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class ReferenceRecreationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def image(self, name: str, size: tuple[int, int] = (198, 140)) -> Path:
        path = self.root / name
        image = Image.new("RGB", size)
        pixels = image.load()
        for y in range(size[1]):
            for x in range(size[0]):
                pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
        image.save(path)
        return path

    @staticmethod
    def full_corners(width: int, height: int) -> dict[str, list[float]]:
        return {
            "top_left": [0.0, 0.0],
            "top_right": [float(width), 0.0],
            "bottom_right": [float(width), float(height)],
            "bottom_left": [0.0, float(height)],
        }

    def test_preflight_is_bounded_and_hashes_source(self) -> None:
        source = self.image("reference.jpg", (300, 200))
        report = inspect_reference_image(source)

        self.assertTrue(report["ready_for_calibration"])
        self.assertEqual(report["width_pixels_after_exif"], 300)
        self.assertEqual(report["height_pixels_after_exif"], 200)
        self.assertEqual(report["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertTrue(any("JPEG" in warning for warning in report["warnings"]))

    def test_calibration_maps_all_photo_corners_to_a4(self) -> None:
        corners = {
            "top_left": [100.0, 50.0],
            "top_right": [1100.0, 80.0],
            "bottom_right": [1050.0, 820.0],
            "bottom_left": [80.0, 850.0],
        }
        calibration = calibrate_a4_landscape(1200, 900, corners)
        rectified = calibration["rectified_image"]
        self.assertEqual(rectified["width_pixels"] * 70, rectified["height_pixels"] * 99)

        coefficients = calibration["transforms"]["rotated_source_pixel_to_corel_mm"]["coefficients"]
        expected = {
            "top_left": (0.0, 210.0),
            "top_right": (297.0, 210.0),
            "bottom_right": (297.0, 0.0),
            "bottom_left": (0.0, 0.0),
        }
        for name in CORNER_NAMES:
            actual = apply_projective_transform(coefficients, corners[name])
            self.assertAlmostEqual(actual[0], expected[name][0], places=7)
            self.assertAlmostEqual(actual[1], expected[name][1], places=7)

    def test_corner_validation_rejects_wrong_order_and_out_of_bounds(self) -> None:
        bow_tie = {
            "top_left": [0, 0],
            "top_right": [100, 100],
            "bottom_right": [100, 0],
            "bottom_left": [0, 100],
        }
        with self.assertRaisesRegex(ReferencePreparationError, "convex quadrilateral"):
            validate_page_corners(bow_tie, 100, 100)

        outside = self.full_corners(100, 100)
        outside["top_left"] = [-1, 0]
        with self.assertRaisesRegex(ReferencePreparationError, "outside"):
            validate_page_corners(outside, 100, 100)

    def test_extrapolated_corners_require_explicit_bounded_opt_in(self) -> None:
        corners = {
            "top_left": [0, 0],
            "top_right": [100, 0],
            "bottom_right": [110, 100],
            "bottom_left": [-10, 100],
        }
        with self.assertRaisesRegex(ReferencePreparationError, "outside"):
            calibrate_a4_landscape(100, 100, corners)

        calibration = calibrate_a4_landscape(
            100,
            100,
            corners,
            allow_extrapolated_corners=True,
        )
        quadrilateral = calibration["page_quadrilateral"]
        self.assertTrue(quadrilateral["uses_explicit_extrapolation"])
        self.assertEqual(
            quadrilateral["corners_outside_image"],
            ["bottom_right", "bottom_left"],
        )

        corners["bottom_right"] = [151, 100]
        with self.assertRaisesRegex(ReferencePreparationError, "permitted"):
            calibrate_a4_landscape(
                100,
                100,
                corners,
                allow_extrapolated_corners=True,
            )

    def test_inner_field_records_physical_margins(self) -> None:
        calibration = calibrate_a4_landscape(990, 700, self.full_corners(990, 700))
        inner = {
            "top_left": [20, 20],
            "top_right": [970, 20],
            "bottom_right": [970, 680],
            "bottom_left": [20, 680],
        }
        measured = measure_inner_printed_field(calibration, inner)
        margins = measured["margin_widths_mm"]
        self.assertAlmostEqual(margins["left"], 6.0, places=6)
        self.assertAlmostEqual(margins["right"], 6.0, places=6)
        self.assertAlmostEqual(margins["top"], 6.0, places=6)
        self.assertAlmostEqual(margins["bottom"], 6.0, places=6)

    def test_rotation_and_rectification_write_reference_only_pngs(self) -> None:
        source = self.image("portrait.png", (140, 198))
        rotated_path = self.root / "rotated.png"
        rotated = save_rotated_reference(
            source, rotated_path, rotation="counterclockwise_90"
        )
        self.assertEqual((rotated["width_pixels"], rotated["height_pixels"]), (198, 140))

        rectified_path = self.root / "rectified.png"
        calibration = rectify_a4_reference(
            source,
            rectified_path,
            self.full_corners(198, 140),
            rotation="counterclockwise_90",
        )
        with Image.open(rectified_path) as image:
            self.assertEqual(
                image.size,
                (
                    calibration["rectified_image"]["width_pixels"],
                    calibration["rectified_image"]["height_pixels"],
                ),
            )
            self.assertEqual(image.width * 70, image.height * 99)
        self.assertEqual(
            calibration["rectified_analysis_file"]["role"],
            "reference-only; never printable artwork",
        )

    def test_workspace_stages_template_then_measured_calibration(self) -> None:
        source = self.image("source.png", (140, 198))
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        template_workspace = self.root / "v2_template"
        first = prepare_a4_reference_workspace(source, template_workspace)

        self.assertEqual(first["status"], "AWAITING_MEASURED_PAGE_CORNERS")
        self.assertTrue(Path(first["artifacts"]["corner_measurement_template"]).is_file())
        self.assertIsNone(first["artifacts"]["rectified_reference"])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)

        measurements = {
            "schema_version": "a4-corner-measurements-v1",
            "rotation_after_exif": "counterclockwise_90",
            "page_corners_pixels": self.full_corners(198, 140),
            "inner_printed_field_corners_pixels": {
                "top_left": [4, 4],
                "top_right": [194, 4],
                "bottom_right": [194, 136],
                "bottom_left": [4, 136],
            },
            "uncertain_regions": [{"label": "glare", "bounds_pixels": [80, 20, 100, 50]}],
        }
        measurements_path = self.root / "corners.json"
        measurements_path.write_text(json.dumps(measurements), encoding="utf-8")
        measured_workspace = self.root / "v2_measured"
        second = prepare_a4_reference_workspace(
            source,
            measured_workspace,
            corner_measurements_path=measurements_path,
        )

        self.assertEqual(second["status"], "PHASE_1_RECTIFIED_AND_CALIBRATED")
        self.assertTrue(Path(second["artifacts"]["rectified_reference"]).is_file())
        measurement_file = Path(second["artifacts"]["measurement_json"])
        result = json.loads(measurement_file.read_text(encoding="utf-8"))
        self.assertIsNotNone(result["inner_printed_field"])
        self.assertEqual(result["uncertain_regions"][0]["label"], "glare")
        self.assertNotIn(".v2_measured.preparing", measurement_file.read_text(encoding="utf-8"))

    def test_workspace_never_overwrites_existing_directory(self) -> None:
        source = self.image("source.png")
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("preserve", encoding="utf-8")

        with self.assertRaisesRegex(ReferencePreparationError, "Refusing to overwrite"):
            prepare_a4_reference_workspace(source, output, rotation="none")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
