from __future__ import annotations

import tempfile
import unittest

from fake_documents import attach_open_document
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from corel_operator.design_plans import (
    DESIGN_PLAN_SCHEMA,
    MAX_PLAN_ELEMENTS,
    preview_design_plan,
    validate_design_plan,
)
from corel_operator.errors import CorelBridgeError, ErrorCode


class DesignPlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid_plan = {
            "version": "1.0",
            "name": "corporate_card",
            "canvas": {"width_inches": 3.5, "height_inches": 2.0},
            "elements": [
                {
                    "id": "card_bg",
                    "type": "rectangle",
                    "x_inches": 0.0,
                    "y_inches": 0.0,
                    "width_inches": 3.5,
                    "height_inches": 2.0,
                    "fill": {"red": 10, "green": 20, "blue": 40},
                    "outline": {"width_points": 0.5, "red": 255, "green": 255, "blue": 255},
                },
                {
                    "id": "avatar_circle",
                    "type": "ellipse",
                    "x_inches": 0.3,
                    "y_inches": 0.5,
                    "width_inches": 1.0,
                    "height_inches": 1.0,
                    "fill": {"red": 200, "green": 200, "blue": 200},
                },
                {
                    "id": "name_title",
                    "type": "text",
                    "text": "ALEX MERCER",
                    "x_inches": 1.5,
                    "y_inches": 1.2,
                    "font": "Arial",
                    "font_size_points": 14.0,
                    "bold": True,
                    "fill": {"red": 255, "green": 255, "blue": 255},
                },
            ],
            "validations": {
                "expected_element_count": 3,
            },
        }

    def test_validate_valid_plan(self) -> None:
        result = validate_design_plan(self.valid_plan)
        self.assertTrue(result["valid"])
        self.assertTrue(result["ready_for_execution"])
        self.assertEqual(result["blocking_issues"], [])
        self.assertEqual(result["element_count"], 3)
        self.assertEqual(result["elements_by_type"], {"rectangle": 1, "ellipse": 1, "text": 1})
        self.assertEqual(result["warnings"], [])

    def test_design_plan_schema_is_valid_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(DESIGN_PLAN_SCHEMA)

    def test_schema_rejects_unknown_root_and_element_properties(self) -> None:
        plan = dict(self.valid_plan)
        plan["unexpected"] = True
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(ctx.exception.details["path"], "plan")

        plan = dict(self.valid_plan)
        plan["elements"] = [
            {
                "id": "box",
                "type": "rectangle",
                "x_inches": 0,
                "y_inches": 0,
                "width_inches": 1,
                "height_inches": 1,
                "unexpected": True,
            }
        ]
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(ctx.exception.details["path"], "plan.elements[0]")

    def test_schema_rejects_type_specific_missing_fields(self) -> None:
        plan = dict(self.valid_plan)
        plan["elements"] = [{"id": "box", "type": "rectangle"}]
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_schema_rejects_invalid_unit_boolean_number_and_too_many_elements(self) -> None:
        plan = dict(self.valid_plan)
        plan["canvas"] = {"width_inches": True, "height_inches": 2.0, "unit": "mm"}
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

        plan = dict(self.valid_plan)
        plan["elements"] = [
            {
                "id": f"box_{index}",
                "type": "rectangle",
                "x_inches": 0,
                "y_inches": 0,
                "width_inches": 1,
                "height_inches": 1,
            }
            for index in range(MAX_PLAN_ELEMENTS + 1)
        ]
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_runtime_rejects_non_finite_numbers(self) -> None:
        plan = dict(self.valid_plan)
        plan["canvas"] = {"width_inches": float("nan"), "height_inches": 2.0}
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_validate_duplicate_element_id_rejected(self) -> None:
        plan = dict(self.valid_plan)
        plan["elements"] = [
            {"id": "box_01", "type": "rectangle", "x_inches": 0, "y_inches": 0, "width_inches": 1, "height_inches": 1},
            {"id": "box_01", "type": "rectangle", "x_inches": 1, "y_inches": 1, "width_inches": 1, "height_inches": 1},
        ]
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertIn("Duplicate element id", str(ctx.exception))

    def test_validate_version_mismatch(self) -> None:
        plan = dict(self.valid_plan)
        plan["version"] = "2.0"
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_validate_unsupported_type(self) -> None:
        plan = dict(self.valid_plan)
        plan["elements"] = [{"id": "star1", "type": "star"}]
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_validate_negative_dimensions(self) -> None:
        plan = dict(self.valid_plan)
        plan["elements"] = [
            {"id": "bad_box", "type": "rectangle", "x_inches": 0, "y_inches": 0, "width_inches": -1, "height_inches": 2}
        ]
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_validate_invalid_color_values(self) -> None:
        plan = dict(self.valid_plan)
        plan["elements"] = [
            {
                "id": "box", "type": "rectangle", "x_inches": 0, "y_inches": 0, "width_inches": 1, "height_inches": 1,
                "fill": {"red": 300, "green": 0, "blue": 0}
            }
        ]
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_validate_expected_count_mismatch(self) -> None:
        plan = dict(self.valid_plan)
        plan["validations"] = {"expected_element_count": 10}
        with self.assertRaises(CorelBridgeError) as ctx:
            validate_design_plan(plan)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_validate_boundary_warnings(self) -> None:
        plan = dict(self.valid_plan)
        plan["validations"] = {
            "expected_element_count": 1,
            "bounding_box_within_canvas": False,
        }
        plan["elements"] = [
            {"id": "overflow_box", "type": "rectangle", "x_inches": 3.0, "y_inches": 1.0, "width_inches": 2.0, "height_inches": 1.0}
        ]
        result = validate_design_plan(plan)
        self.assertTrue(result["valid"])
        self.assertTrue(result["ready_for_execution"])
        self.assertEqual(result["blocking_issues"], [])
        self.assertGreaterEqual(len(result["warnings"]), 1)

    def test_validate_required_canvas_bounds_block_execution_readiness(self) -> None:
        plan = dict(self.valid_plan)
        plan["validations"] = {
            "expected_element_count": 1,
            "bounding_box_within_canvas": True,
        }
        plan["elements"] = [
            {
                "id": "overflow_box",
                "type": "rectangle",
                "x_inches": 3.0,
                "y_inches": 1.0,
                "width_inches": 2.0,
                "height_inches": 1.0,
            }
        ]
        result = validate_design_plan(plan)
        self.assertTrue(result["valid"])
        self.assertFalse(result["ready_for_execution"])
        self.assertGreaterEqual(len(result["blocking_issues"]), 1)
        self.assertEqual(result["warnings"], [])


class DesignPlanPreviewTests(unittest.TestCase):
    def test_preview_design_plan_calculations(self) -> None:
        plan = {
            "version": "1.0",
            "name": "preview_test",
            "description": "Preview test description",
            "canvas": {"width_inches": 10.0, "height_inches": 8.0},
            "elements": [
                {
                    "id": "rect1",
                    "type": "rectangle",
                    "x_inches": 1.0,
                    "y_inches": 1.0,
                    "width_inches": 4.0,
                    "height_inches": 2.0,
                    "fill": {"red": 255, "green": 0, "blue": 0},
                },
                {
                    "id": "rect2",
                    "type": "rectangle",
                    "x_inches": 3.0,
                    "y_inches": 2.0,
                    "width_inches": 4.0,
                    "height_inches": 3.0,
                    "fill": {"red": 0, "green": 128, "blue": 255},
                },
                {
                    "id": "txt1",
                    "type": "text",
                    "text": "HEADER",
                    "x_inches": 2.0,
                    "y_inches": 6.0,
                    "font": "Helvetica",
                    "font_size_points": 36.0,
                    "bold": True,
                },
            ],
        }
        preview = preview_design_plan(plan)
        self.assertTrue(preview["valid"])
        self.assertTrue(preview["ready_for_execution"])
        self.assertEqual(preview["blocking_issues"], [])
        self.assertEqual(preview["name"], "preview_test")
        self.assertEqual(preview["canvas"]["area_sq_inches"], 80.0)
        self.assertEqual(preview["elements_summary"]["total_count"], 3)
        self.assertEqual(preview["elements_summary"]["z_order"], ["rect1", "rect2", "txt1"])

        # Check colors
        colors = preview["color_palette"]["colors_rgb"]
        self.assertIn([255, 0, 0], colors)
        self.assertIn([0, 128, 255], colors)

        # Check typography
        fonts = [t["font"] for t in preview["typography"]]
        self.assertIn("Helvetica", fonts)

        # Check bounding box
        bbox = preview["bounding_box"]
        self.assertEqual(bbox["min_x_inches"], 1.0)
        self.assertEqual(bbox["min_y_inches"], 1.0)
        self.assertGreaterEqual(bbox["max_x_inches"], 7.0)

    def test_preview_reports_blocking_canvas_issues(self) -> None:
        plan = {
            "version": "1.0",
            "name": "blocked_preview",
            "canvas": {"width_inches": 2.0, "height_inches": 2.0},
            "elements": [
                {
                    "id": "overflow",
                    "type": "rectangle",
                    "x_inches": 1.5,
                    "y_inches": 1.5,
                    "width_inches": 1.0,
                    "height_inches": 1.0,
                }
            ],
        }
        preview = preview_design_plan(plan)
        self.assertFalse(preview["ready_for_execution"])
        self.assertGreaterEqual(len(preview["blocking_issues"]), 2)


class _MockShape:
    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.Name = ""
        self.PositionX = x
        self.PositionY = y
        self.SizeWidth = w
        self.SizeHeight = h
        self.Fill = _MockFill()
        self.Outline = _MockOutline()

    def SetPosition(self, x: float, y: float) -> None:
        self.PositionX = x
        self.PositionY = y


class _MockFill:
    def __init__(self) -> None:
        self.applied_color = None

    def ApplyUniformFill(self, color: Any) -> None:
        self.applied_color = color


class _MockOutline:
    def __init__(self) -> None:
        self.Width = 0.0
        self.Color = None
        self.no_outline = False

    def SetNoOutline(self) -> None:
        self.no_outline = True
        self.Width = 0.0


class _MockLayer:
    def __init__(self, shapes: list[_MockShape]) -> None:
        self.shapes = shapes

    def CreateRectangle2(self, x, y, width, height):
        shape = _MockShape(x, y, width, height)
        self.shapes.append(shape)
        return shape

    def CreateEllipse2(self, cx, cy, r1, r2):
        shape = _MockShape(cx - r1, cy - r2, r1 * 2, r2 * 2)
        self.shapes.append(shape)
        return shape

    def CreateArtisticText(self, left, bottom, text, lang, charset, font, size, bold):
        shape = _MockShape(left, bottom, 2.0, 0.5)
        self.shapes.append(shape)
        return shape


class _MockShapesCollection:
    def __init__(self, shapes: list[_MockShape]) -> None:
        self.items = shapes

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _MockPage:
    def __init__(self, width: float = 8.5, height: float = 11.0) -> None:
        self.SizeWidth = width
        self.SizeHeight = height
        self.shapes: list[_MockShape] = []
        self.ActiveLayer = _MockLayer(self.shapes)
        self.Shapes = _MockShapesCollection(self.shapes)

    def GetSize(self):
        return (self.SizeWidth, self.SizeHeight)


class _MockDocument:
    def __init__(self, width: float = 8.5, height: float = 11.0) -> None:
        self.Name = "TestPlanDoc"
        self.Unit = 1
        self.ReferencePoint = 5
        self.ActivePage = _MockPage(width, height)
        self.command_groups: list[str] = []
        self.undo_called = 0
        self.command_group_start_count: int | None = None

    def BeginCommandGroup(self, name: str) -> None:
        self.command_groups.append(name)
        self.command_group_start_count = len(self.ActivePage.shapes)

    def EndCommandGroup(self) -> None:
        pass

    def Undo(self) -> None:
        self.undo_called += 1
        if self.command_group_start_count is not None:
            del self.ActivePage.shapes[self.command_group_start_count:]


class _MockApp:
    def CreateRGBColor(self, r: int, g: int, b: int) -> dict[str, int]:
        return {"red": r, "green": g, "blue": b}


class DesignPlanExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        from corel_operator.corel_bridge import CorelBridge
        self.bridge = CorelBridge()
        self.doc = _MockDocument(8.5, 11.0)
        self.bridge.app = _MockApp()
        attach_open_document(self.bridge, self.doc)

    def test_execute_design_plan_rejects_blocking_preflight_before_com(self) -> None:
        plan = {
            "version": "1.0",
            "name": "blocked_execution",
            "canvas": {"width_inches": 2.0, "height_inches": 2.0},
            "elements": [
                {
                    "id": "overflow",
                    "type": "rectangle",
                    "x_inches": 1.5,
                    "y_inches": 1.5,
                    "width_inches": 1.0,
                    "height_inches": 1.0,
                }
            ],
        }

        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.execute_design_plan(plan)

        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertGreaterEqual(len(ctx.exception.details["blocking_issues"]), 2)
        self.assertEqual(self.doc.command_groups, [])
        self.assertEqual(self.doc.ActivePage.shapes, [])

    def test_execute_design_plan_success(self) -> None:
        plan = {
            "version": "1.0",
            "name": "full_exec_plan",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0},
            "elements": [
                {
                    "id": "header_panel",
                    "type": "rectangle",
                    "x_inches": 0.5,
                    "y_inches": 9.0,
                    "width_inches": 7.5,
                    "height_inches": 1.5,
                    "fill": {"red": 15, "green": 45, "blue": 90},
                    "outline": {"width_points": 0.0},
                },
                {
                    "id": "circle_icon",
                    "type": "ellipse",
                    "x_inches": 1.0,
                    "y_inches": 9.2,
                    "width_inches": 1.0,
                    "height_inches": 1.0,
                    "fill": {"red": 255, "green": 215, "blue": 0},
                },
                {
                    "id": "main_title",
                    "type": "text",
                    "text": "SUMMIT 2026",
                    "x_inches": 2.5,
                    "y_inches": 9.5,
                    "font": "Arial",
                    "font_size_points": 28.0,
                    "bold": True,
                    "fill": {"red": 255, "green": 255, "blue": 255},
                    "outline": {"width_points": 1.5, "red": 1, "green": 2, "blue": 3},
                },
            ],
        }
        result = self.bridge.execute_design_plan(plan)
        self.assertTrue(result["executed"])
        self.assertEqual(result["elements_executed"], 3)
        self.assertEqual(result["object_names"], ["header_panel", "circle_icon", "main_title"])
        self.assertTrue(result["post_execution_verification"])
        self.assertEqual(result["elements"][0]["object_names"], ["header_panel"])
        self.assertEqual(result["elements"][0]["actual_objects"][0]["x_inches"], 0.5)
        self.assertEqual(result["elements"][1]["actual_objects"][0]["width_inches"], 1.0)
        self.assertEqual(len(self.doc.ActivePage.shapes), 3)
        self.assertEqual(len(self.doc.command_groups), 1)
        self.assertEqual(self.doc.undo_called, 0)

        rectangle, ellipse, text = self.doc.ActivePage.shapes
        self.assertEqual(rectangle.Fill.applied_color, {"red": 15, "green": 45, "blue": 90})
        self.assertTrue(rectangle.Outline.no_outline)
        self.assertEqual(ellipse.Fill.applied_color, {"red": 255, "green": 215, "blue": 0})
        self.assertEqual(text.Fill.applied_color, {"red": 255, "green": 255, "blue": 255})
        self.assertAlmostEqual(text.Outline.Width, 1.5 / 72.0, places=4)
        self.assertEqual(text.Outline.Color, {"red": 1, "green": 2, "blue": 3})

    def test_execute_design_plan_artwork_uses_import_move_and_resize(self) -> None:
        imported_paths: list[str] = []

        def fake_import(file_path: str, object_name: str) -> dict[str, Any]:
            imported_paths.append(file_path)
            shape = _MockShape(0.0, 0.0, 1.0, 1.0)
            shape.Name = object_name
            self.doc.ActivePage.shapes.append(shape)
            return {
                "imported": True,
                "object_names": [object_name],
                "objects": [],
            }

        self.bridge.import_artwork = fake_import  # type: ignore[method-assign]
        with tempfile.TemporaryDirectory() as directory:
            artwork_path = Path(directory) / "logo.svg"
            artwork_path.write_text("<svg/>", encoding="utf-8")
            plan = {
                "version": "1.0",
                "name": "artwork_plan",
                "canvas": {"width_inches": 8.5, "height_inches": 11.0},
                "elements": [
                    {
                        "id": "logo",
                        "type": "artwork",
                        "file_path": str(artwork_path),
                        "x_inches": 2.0,
                        "y_inches": 3.0,
                        "width_inches": 4.0,
                    }
                ],
            }

            result = self.bridge.execute_design_plan(plan)

        self.assertTrue(result["executed"])
        self.assertEqual(imported_paths, [str(artwork_path)])
        self.assertEqual(result["object_names"], ["logo"])
        shape = self.doc.ActivePage.shapes[0]
        self.assertEqual((shape.PositionX, shape.PositionY), (2.0, 3.0))
        self.assertEqual((shape.SizeWidth, shape.SizeHeight), (4.0, 4.0))

    def test_execute_design_plan_preflights_artwork_before_document_creation(self) -> None:
        create_calls: list[tuple[float, float]] = []
        self.bridge.create_document = (  # type: ignore[method-assign]
            lambda width_in, height_in: create_calls.append((width_in, height_in))
        )
        with tempfile.TemporaryDirectory() as directory:
            plan = {
                "version": "1.0",
                "name": "missing_artwork",
                "canvas": {"width_inches": 8.5, "height_inches": 11.0},
                "elements": [
                    {
                        "id": "logo",
                        "type": "artwork",
                        "file_path": str(Path(directory) / "missing.svg"),
                    }
                ],
            }

            with self.assertRaises(CorelBridgeError) as ctx:
                self.bridge.execute_design_plan(plan, create_new_document=True)

        self.assertEqual(ctx.exception.code, ErrorCode.UNSAFE_PATH)
        self.assertEqual(create_calls, [])
        self.assertEqual(self.doc.command_groups, [])

    def test_execute_design_plan_reports_post_execution_discrepancy(self) -> None:
        self.bridge.list_objects = lambda max_objects=200: {  # type: ignore[method-assign]
            "objects": [],
            "total_on_page": 1,
        }
        plan = {
            "version": "1.0",
            "name": "discrepancy_plan",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0},
            "elements": [
                {
                    "id": "box",
                    "type": "rectangle",
                    "x_inches": 1.0,
                    "y_inches": 1.0,
                    "width_inches": 1.0,
                    "height_inches": 1.0,
                }
            ],
        }

        result = self.bridge.execute_design_plan(plan)

        self.assertFalse(result["post_execution_verification"])
        self.assertEqual(len(result["discrepancies"]), 1)
        self.assertIn("box", result["discrepancies"][0])

    def test_execute_design_plan_atomic_rollback_on_failure(self) -> None:
        existing = _MockShape(0.0, 0.0, 0.5, 0.5)
        existing.Name = "existing_shape"
        self.doc.ActivePage.shapes.append(existing)

        # Create a layer that fails on step 2
        class _FailingLayer(_MockLayer):
            def CreateEllipse2(self, *args, **kwargs):
                raise RuntimeError("Simulated COM ellipse crash")

        self.doc.ActivePage.ActiveLayer = _FailingLayer(self.doc.ActivePage.shapes)

        plan = {
            "version": "1.0",
            "name": "failing_plan",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0},
            "elements": [
                {"id": "box1", "type": "rectangle", "x_inches": 1, "y_inches": 1, "width_inches": 2, "height_inches": 2},
                {"id": "bad_ellipse", "type": "ellipse", "x_inches": 3, "y_inches": 3, "width_inches": 2, "height_inches": 2},
            ],
        }

        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.execute_design_plan(plan, rollback_on_failure=True)

        self.assertIn("Plan execution failed on element 'bad_ellipse'", str(ctx.exception))
        self.assertNotIn("Simulated COM ellipse crash", str(ctx.exception))
        self.assertIn("Changes were rolled back", str(ctx.exception))
        self.assertEqual(self.doc.undo_called, 1)
        self.assertEqual(self.doc.ActivePage.shapes, [existing])
        rollback = ctx.exception.details["rollback"]
        self.assertTrue(rollback["attempted"])
        self.assertTrue(rollback["undo_succeeded"])
        self.assertTrue(rollback["verified"])
        self.assertEqual(rollback["before_count"], 1)
        self.assertEqual(rollback["after_count"], 1)

    def test_execute_design_plan_rolls_back_when_command_group_close_fails(self) -> None:
        class _EndFailDocument(_MockDocument):
            def EndCommandGroup(self) -> None:
                raise RuntimeError("sensitive command-group close failure")

        doc = _EndFailDocument(8.5, 11.0)
        attach_open_document(self.bridge, doc)
        plan = {
            "version": "1.0",
            "name": "end_group_failure",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0},
            "elements": [
                {
                    "id": "box",
                    "type": "rectangle",
                    "x_inches": 1.0,
                    "y_inches": 1.0,
                    "width_inches": 1.0,
                    "height_inches": 1.0,
                }
            ],
        }

        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.execute_design_plan(plan, rollback_on_failure=True)

        self.assertEqual(ctx.exception.code, ErrorCode.COREL_COM_ERROR)
        self.assertNotIn("sensitive command-group close failure", str(ctx.exception))
        self.assertTrue(ctx.exception.details["rollback"]["verified"])
        self.assertFalse(ctx.exception.details["rollback"]["command_group_closed"])
        self.assertEqual(doc.undo_called, 1)
        self.assertEqual(doc.ActivePage.shapes, [])

    def test_execute_design_plan_does_not_claim_unverified_rollback(self) -> None:
        class _FailingLayer(_MockLayer):
            def CreateEllipse2(self, *args, **kwargs):
                raise RuntimeError("Simulated COM ellipse crash")

        class _NoOpUndoDocument(_MockDocument):
            def Undo(self) -> None:
                self.undo_called += 1

        self.doc = _NoOpUndoDocument(8.5, 11.0)
        self.doc.ActivePage.ActiveLayer = _FailingLayer(self.doc.ActivePage.shapes)
        attach_open_document(self.bridge, self.doc)
        plan = {
            "version": "1.0",
            "name": "unverified_rollback",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0},
            "elements": [
                {"id": "box1", "type": "rectangle", "x_inches": 1, "y_inches": 1, "width_inches": 2, "height_inches": 2},
                {"id": "bad_ellipse", "type": "ellipse", "x_inches": 3, "y_inches": 3, "width_inches": 2, "height_inches": 2},
            ],
        }

        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.execute_design_plan(plan, rollback_on_failure=True)

        self.assertIn("Rollback could not be verified", str(ctx.exception))
        self.assertFalse(ctx.exception.details["rollback"]["verified"])
        self.assertEqual(ctx.exception.details["rollback"]["created_objects_remaining"], ["box1"])
        self.assertEqual(len(self.doc.ActivePage.shapes), 1)

    def test_execute_design_plan_requires_command_group_when_rollback_requested(self) -> None:
        class _NoCommandGroupDocument(_MockDocument):
            def BeginCommandGroup(self, name: str) -> None:
                raise RuntimeError("Command groups unavailable")

        self.doc = _NoCommandGroupDocument(8.5, 11.0)
        attach_open_document(self.bridge, self.doc)
        plan = {
            "version": "1.0",
            "name": "no_command_group",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0},
            "elements": [
                {"id": "box", "type": "rectangle", "x_inches": 1, "y_inches": 1, "width_inches": 2, "height_inches": 2},
            ],
        }

        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.execute_design_plan(plan, rollback_on_failure=True)

        self.assertIn("Could not start a CorelDRAW command group", str(ctx.exception))
        self.assertEqual(self.doc.ActivePage.shapes, [])


if __name__ == "__main__":
    unittest.main()
