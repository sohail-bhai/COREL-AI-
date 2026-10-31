from __future__ import annotations

import unittest
from typing import Any

from corel_operator.design_plans import preview_design_plan, validate_design_plan
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
        self.assertEqual(result["element_count"], 3)
        self.assertEqual(result["elements_by_type"], {"rectangle": 1, "ellipse": 1, "text": 1})
        self.assertEqual(result["warnings"], [])

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
        plan["validations"] = {"expected_element_count": 1}
        plan["elements"] = [
            {"id": "overflow_box", "type": "rectangle", "x_inches": 3.0, "y_inches": 1.0, "width_inches": 2.0, "height_inches": 1.0}
        ]
        result = validate_design_plan(plan)
        self.assertTrue(result["valid"])
        self.assertGreaterEqual(len(result["warnings"]), 1)


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

    def BeginCommandGroup(self, name: str) -> None:
        self.command_groups.append(name)

    def EndCommandGroup(self) -> None:
        pass

    def Undo(self) -> None:
        self.undo_called += 1
        # Roll back all shapes added
        self.ActivePage.shapes.clear()


class _MockApp:
    def CreateRGBColor(self, r: int, g: int, b: int) -> dict[str, int]:
        return {"red": r, "green": g, "blue": b}


class DesignPlanExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        from corel_operator.corel_bridge import CorelBridge
        self.bridge = CorelBridge()
        self.doc = _MockDocument(8.5, 11.0)
        self.bridge.target_doc = self.doc
        self.bridge.app = _MockApp()

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
                },
            ],
        }
        result = self.bridge.execute_design_plan(plan)
        self.assertTrue(result["executed"])
        self.assertEqual(result["elements_executed"], 3)
        self.assertEqual(result["object_names"], ["header_panel", "circle_icon", "main_title"])
        self.assertTrue(result["post_execution_verification"])
        self.assertEqual(len(self.doc.ActivePage.shapes), 3)
        self.assertEqual(len(self.doc.command_groups), 1)
        self.assertEqual(self.doc.undo_called, 0)

    def test_execute_design_plan_atomic_rollback_on_failure(self) -> None:
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
        self.assertIn("Changes were rolled back", str(ctx.exception))
        # Ensure Undo was called to revert partial shapes
        self.assertEqual(self.doc.undo_called, 1)
        self.assertEqual(len(self.doc.ActivePage.shapes), 0)


if __name__ == "__main__":
    unittest.main()
