from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.print_jobs import inspect_raster_artwork, plan_print_job


TEMP_ROOT = Path(tempfile.gettempdir()) / "opencode"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class _Shapes:
    def __init__(self) -> None:
        self.items = []

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _PrintShape:
    Type = 6

    def __init__(self, owner: _Shapes, layer, page, static_id: int) -> None:
        self.owner = owner
        self.Layer = layer
        self.Page = page
        self.StaticID = static_id
        self.Name = ""
        self.PositionX = 0.0
        self.PositionY = 0.0
        self.SizeWidth = 4.0
        self.SizeHeight = 6.0

    def SetPosition(self, x: float, y: float) -> None:
        self.PositionX = x
        self.PositionY = y

    def Rotate(self, degrees: float) -> None:
        if int(degrees) % 180:
            self.SizeWidth, self.SizeHeight = self.SizeHeight, self.SizeWidth

    def Duplicate(self, offset_x: float, offset_y: float):
        duplicate = _PrintShape(self.owner, self.Layer, self.Page, self.StaticID + len(self.owner.items) + 1)
        duplicate.PositionX = self.PositionX + offset_x
        duplicate.PositionY = self.PositionY + offset_y
        self.owner.items.append(duplicate)
        return duplicate


class _PrintLayer:
    Name = "Layer 1"

    def __init__(self) -> None:
        self.document = None
        self.import_paths: list[str] = []
        self.import_files_existed: list[bool] = []

    def Import(self, file_path: str, *args) -> None:
        self.import_paths.append(file_path)
        self.import_files_existed.append(Path(file_path).is_file())
        shape = _PrintShape(self.document.ActivePage.Shapes, self, self.document.ActivePage, 100)
        self.document.ActivePage.Shapes.items.append(shape)
        selected = _Shapes()
        selected.items.append(shape)
        self.document.SelectionRange = selected


class _PrintPage:
    Index = 1

    def __init__(self, layer: _PrintLayer) -> None:
        self.ActiveLayer = layer
        self.Shapes = _Shapes()
        self.SizeWidth = 8.5
        self.SizeHeight = 11.0

    def SetSize(self, width: float, height: float) -> None:
        self.SizeWidth = width
        self.SizeHeight = height

    def GetSize(self):
        return self.SizeWidth, self.SizeHeight


class _PrintDocument:
    Name = "PrintJob"

    def __init__(self) -> None:
        self.Unit = 1
        self.ReferencePoint = 5
        layer = _PrintLayer()
        self.ActivePage = _PrintPage(layer)
        layer.document = self
        self.SelectionRange = _Shapes()
        self.undo_called = False

    def Activate(self) -> None:
        pass

    def ClearSelection(self) -> None:
        self.SelectionRange = _Shapes()

    def BeginCommandGroup(self, name: str) -> None:
        pass

    def EndCommandGroup(self) -> None:
        pass

    def Undo(self) -> None:
        self.undo_called = True
        self.ActivePage.Shapes.items.clear()


class _PrintApplication:
    def __init__(self) -> None:
        self.document = None

    def CreateDocument(self):
        self.document = _PrintDocument()
        return self.document

    @staticmethod
    def CreateStructImportOptions():
        return object()


class PrintJobPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def image(self, name: str, size: tuple[int, int], mode: str = "RGB") -> Path:
        path = self.root / name
        Image.new(mode, size, 0).save(path)
        return path

    def assert_code(self, code: ErrorCode, callback, *args, **kwargs) -> None:
        with self.assertRaises(CorelBridgeError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_inspection_reports_pixel_color_and_profile_metadata(self) -> None:
        path = self.image("art.png", (1200, 1800), "RGBA")

        result = inspect_raster_artwork(str(path))

        self.assertEqual(result["width_pixels"], 1200)
        self.assertEqual(result["height_pixels"], 1800)
        self.assertEqual(result["color_space"], "rgb_alpha")
        self.assertTrue(result["has_alpha"])
        self.assertFalse(result["has_icc_profile"])

    def test_valid_job_returns_deterministic_trim_and_artwork_boxes(self) -> None:
        path = self.image("poster.png", (1200, 1800))

        result = plan_print_job(str(path), 4, 6, 13, 19, copies=4, margin_inches=0.5, gutter_inches=0.25)

        self.assertTrue(result["ready_for_execution"])
        self.assertEqual(result["layout"]["capacity"], 4)
        self.assertEqual(len(result["placements"]), 4)
        self.assertEqual(result["effective_dpi"]["minimum"], 300.0)
        self.assertEqual(result["placements"][0]["artwork_box"], {
            "x_inches": 0.5,
            "y_inches": 12.5,
            "width_inches": 4.0,
            "height_inches": 6.0,
        })
        self.assertEqual(result["placements"][0]["trim_box"], result["placements"][0]["artwork_box"])
        self.assertEqual(result["placements"][0]["safe_box"], {
            "x_inches": 0.625,
            "y_inches": 12.625,
            "width_inches": 3.75,
            "height_inches": 5.75,
        })

    def test_bleed_requires_explicit_artwork_confirmation(self) -> None:
        path = self.image("bleed.png", (1275, 1875))

        blocked = plan_print_job(str(path), 4, 6, 13, 19, bleed_inches=0.125)
        approved = plan_print_job(
            str(path), 4, 6, 13, 19, bleed_inches=0.125,
            artwork_includes_bleed=True,
        )

        self.assertFalse(blocked["ready_for_execution"])
        self.assertIn("BLEED_NOT_CONFIRMED", [item["code"] for item in blocked["preflight"]["blocking_issues"]])
        self.assertTrue(approved["ready_for_execution"])
        self.assertEqual(approved["placements"][0]["trim_box"]["x_inches"], 0.375)

    def test_low_resolution_blocks_unless_explicitly_allowed(self) -> None:
        path = self.image("low.png", (400, 600))

        blocked = plan_print_job(str(path), 4, 6, 13, 19, minimum_dpi=150)
        allowed = plan_print_job(
            str(path), 4, 6, 13, 19, minimum_dpi=150,
            allow_low_resolution=True,
        )

        self.assertFalse(blocked["ready_for_execution"])
        self.assertTrue(allowed["ready_for_execution"])
        self.assertEqual(allowed["effective_dpi"]["minimum"], 100.0)

    def test_aspect_fit_modes_preserve_crop_or_explicitly_distort(self) -> None:
        path = self.image("square.png", (1200, 1200))

        contained = plan_print_job(str(path), 4, 6, 8.5, 11, fit_mode="contain")
        covered = plan_print_job(str(path), 4, 6, 8.5, 11, fit_mode="cover")
        stretched = plan_print_job(str(path), 4, 6, 8.5, 11, fit_mode="stretch")

        self.assertEqual(contained["placements"][0]["artwork_box"]["height_inches"], 4.0)
        self.assertFalse(contained["aspect_fit"]["cropped"])
        self.assertEqual(covered["placements"][0]["artwork_box"]["height_inches"], 6.0)
        self.assertEqual(covered["aspect_fit"]["source_crop_pixels"]["width"], 800)
        self.assertTrue(covered["aspect_fit"]["cropped"])
        self.assertTrue(stretched["aspect_fit"]["distorted"])
        self.assertEqual(covered["effective_dpi"]["minimum"], 200.0)

    def test_sheet_overflow_is_reported(self) -> None:
        path = self.image("poster.png", (1200, 1800))

        result = plan_print_job(str(path), 4, 6, 8.5, 11, copies=2)

        codes = [item["code"] for item in result["preflight"]["blocking_issues"]]
        self.assertIn("COPY_COUNT_EXCEEDS_SHEET", codes)

    def test_best_fit_reports_mixed_rotation_and_production_quantity(self) -> None:
        path = self.image("gangup.png", (1500, 600))

        result = plan_print_job(
            str(path), 5, 2, 9, 14,
            copies=100,
            margin_inches=0,
            gutter_inches=0,
            rotation_policy="best_fit",
        )

        self.assertEqual(result["layout"]["layout_strategy"], "mixed_rotated_columns")
        self.assertEqual(result["copies_per_sheet"], 11)
        self.assertEqual(result["sheets_required"], 10)
        self.assertEqual(result["total_produced"], 110)
        self.assertEqual(result["overage"], 10)
        self.assertEqual(len(result["placements"]), 11)
        self.assertEqual(sum(item["rotation_degrees"] == 90 for item in result["placements"]), 4)
        self.assertIn("COPY_COUNT_EXCEEDS_SHEET", [
            item["code"] for item in result["preflight"]["blocking_issues"]
        ])

    def test_best_fit_centers_an_incomplete_strip(self) -> None:
        path = self.image("partial-gangup.png", (1500, 600))

        result = plan_print_job(
            str(path), 5, 2, 9, 14,
            copies=8,
            margin_inches=0,
            gutter_inches=0,
            rotation_policy="best_fit",
        )

        rotated = result["placements"][7]
        self.assertEqual(rotated["rotation_degrees"], 90)
        self.assertEqual(rotated["placement_box"]["y_inches"], 4.5)
        self.assertEqual(rotated["placement_box"]["width_inches"], 2.0)
        self.assertEqual(rotated["placement_box"]["height_inches"], 5.0)

    def test_contain_mode_cannot_claim_mismatched_bleed_coverage(self) -> None:
        path = self.image("square-bleed.png", (1200, 1200))

        result = plan_print_job(
            str(path), 4, 6, 8.5, 11,
            bleed_inches=0.125, artwork_includes_bleed=True, fit_mode="contain",
        )

        codes = [item["code"] for item in result["preflight"]["blocking_issues"]]
        self.assertIn("BLEED_COVERAGE_INCOMPLETE", codes)

    def test_invalid_raster_and_boolean_inputs_use_stable_errors(self) -> None:
        text_path = self.root / "art.svg"
        text_path.write_text("<svg/>", encoding="utf-8")
        image_path = self.image("art.png", (1200, 1800))

        self.assert_code(ErrorCode.INVALID_ARGUMENT, inspect_raster_artwork, str(text_path))
        self.assert_code(
            ErrorCode.INVALID_ARGUMENT,
            plan_print_job,
            str(image_path), 4, 6, 13, 19,
            artwork_includes_bleed=1,
        )
        self.assert_code(
            ErrorCode.INVALID_ARGUMENT,
            plan_print_job,
            str(image_path), 4, 6, 13, 19,
            fit_mode="unknown",
        )
        self.assert_code(
            ErrorCode.INVALID_ARGUMENT,
            plan_print_job,
            str(image_path), 0.2, 6, 13, 19,
            safe_margin_inches=0.1,
        )


class PrintJobExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.path = Path(self.temp_dir.name) / "poster.png"
        Image.new("RGB", (1200, 1800), 0).save(self.path)
        self.application = _PrintApplication()
        self.bridge = CorelBridge()
        self.bridge.app = self.application

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_prepare_print_job_creates_new_sheet_and_named_copies(self) -> None:
        result = self.bridge.prepare_print_job(
            str(self.path), 4, 6, 13, 19,
            copies=4, margin_inches=0.5, gutter_inches=0.25,
            object_name_prefix="Poster",
        )

        self.assertTrue(result["prepared"])
        self.assertEqual(result["created_count"], 4)
        self.assertTrue(result["post_execution_verification"])
        self.assertEqual(
            [item["object_name"] for item in result["objects"]],
            ["Poster_001", "Poster_002", "Poster_003", "Poster_004"],
        )
        self.assertEqual(result["objects"][0]["actual_bounds_inches"], {
            "x": 0.5, "y": 12.5, "width": 4.0, "height": 6.0,
        })
        self.assertFalse(result["plan"]["print_ready"])
        self.assertEqual(self.application.document.ActivePage.GetSize(), (13.0, 19.0))

    def test_cover_mode_imports_a_lossless_cropped_derivative(self) -> None:
        square = Path(self.temp_dir.name) / "square.png"
        Image.new("RGB", (1200, 1200), 0).save(square)

        result = self.bridge.prepare_print_job(
            str(square), 4, 6, 8.5, 11,
            fit_mode="cover",
        )

        layer = self.application.document.ActivePage.ActiveLayer
        self.assertTrue(result["plan"]["aspect_fit"]["cropped"])
        self.assertEqual(result["plan"]["aspect_fit"]["source_crop_pixels"]["width"], 800)
        self.assertTrue(layer.import_files_existed[0])
        self.assertTrue(layer.import_paths[0].lower().endswith(".tif"))
        self.assertFalse(Path(layer.import_paths[0]).exists())
        self.assertEqual(result["objects"][0]["actual_bounds_inches"]["width"], 4.0)
        self.assertEqual(result["objects"][0]["actual_bounds_inches"]["height"], 6.0)

    def test_prepare_print_job_executes_per_copy_rotation(self) -> None:
        gangup = Path(self.temp_dir.name) / "gangup.png"
        Image.new("RGB", (1500, 600), 0).save(gangup)

        result = self.bridge.prepare_print_job(
            str(gangup), 5, 2, 9, 14,
            copies=11,
            margin_inches=0,
            gutter_inches=0,
            rotation_policy="best_fit",
        )

        self.assertEqual(result["created_count"], 11)
        self.assertEqual(sum(item["rotation_degrees"] == 90 for item in result["objects"]), 4)
        rotated = [item for item in result["objects"] if item["rotation_degrees"] == 90]
        self.assertEqual(rotated[0]["actual_bounds_inches"]["width"], 2.0)
        self.assertEqual(rotated[0]["actual_bounds_inches"]["height"], 5.0)

    def test_failed_preflight_does_not_create_document(self) -> None:
        low_resolution = Path(self.temp_dir.name) / "low.png"
        Image.new("RGB", (200, 300), 0).save(low_resolution)

        with self.assertRaises(CorelBridgeError) as caught:
            self.bridge.prepare_print_job(str(low_resolution), 4, 6, 13, 19)

        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertIsNone(self.application.document)


if __name__ == "__main__":
    unittest.main()
