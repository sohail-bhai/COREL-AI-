from __future__ import annotations

import unittest

from fake_documents import attach_open_document

from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.workflows import (
    MAX_CHEST_NUMBER_SEQUENCE,
    MAX_LAYOUT_PLACEMENTS,
    build_chest_number_sequence,
    calculate_sheet_layout,
)


class WorkflowTests(unittest.TestCase):
    def test_calculate_sheet_layout_basic(self) -> None:
        # 2 x 3 inches item on an 8.5 x 11 inches sheet with 0.5 margin
        # Usable width: 8.5 - 1.0 = 7.5; Usable height: 11 - 1.0 = 10.0
        # Unrotated: 2 in W -> 7.5 / 2 = 3 cols; 3 in H -> 10.0 / 3 = 3 rows -> 9 items
        # Rotated: 3 in W -> 7.5 / 3 = 2 cols; 2 in H -> 10.0 / 2 = 5 rows -> 10 items (Rotated wins!)
        layout = calculate_sheet_layout(
            item_width_inches=2.0,
            item_height_inches=3.0,
            sheet_width_inches=8.5,
            sheet_height_inches=11.0,
            margin_inches=0.5,
            gutter_inches=0.0,
            allow_rotate=True,
        )
        self.assertTrue(layout["fits"])
        self.assertTrue(layout["rotated"])
        self.assertEqual(layout["columns"], 2)
        self.assertEqual(layout["rows"], 5)
        self.assertEqual(layout["capacity"], 10)
        self.assertEqual(len(layout["placements"]), 10)
        self.assertEqual(layout["usable_width_inches"], 7.5)
        self.assertEqual(layout["usable_height_inches"], 10.0)

        first = layout["placements"][0]
        self.assertEqual(first["row"], 1)
        self.assertEqual(first["column"], 1)
        self.assertEqual(first["width_inches"], 3.0)
        self.assertEqual(first["height_inches"], 2.0)
        self.assertEqual(first["x_inches"], 0.5)

    def test_calculate_sheet_layout_without_rotation(self) -> None:
        layout = calculate_sheet_layout(
            item_width_inches=2.0,
            item_height_inches=3.0,
            sheet_width_inches=8.5,
            sheet_height_inches=11.0,
            margin_inches=0.5,
            allow_rotate=False,
        )
        self.assertFalse(layout["rotated"])
        self.assertEqual(layout["columns"], 3)
        self.assertEqual(layout["rows"], 3)
        self.assertEqual(layout["capacity"], 9)
        self.assertEqual(len(layout["placements"]), 9)

    def test_calculate_sheet_layout_with_gutters(self) -> None:
        # Usable width: 10 - 2 = 8; Usable height: 10 - 2 = 8
        # Item: 3 x 3, Gutter: 1
        # count = (8 + 1) / (3 + 1) = 9 / 4 = 2 cols and 2 rows -> 4 items
        layout = calculate_sheet_layout(
            item_width_inches=3.0,
            item_height_inches=3.0,
            sheet_width_inches=10.0,
            sheet_height_inches=10.0,
            margin_inches=1.0,
            gutter_inches=1.0,
        )
        self.assertEqual(layout["columns"], 2)
        self.assertEqual(layout["rows"], 2)
        self.assertEqual(layout["capacity"], 4)
        p1 = layout["placements"][0]
        p2 = layout["placements"][1]
        self.assertEqual(p1["x_inches"], 1.0)
        self.assertEqual(p2["x_inches"], 5.0)  # 1.0 + 3.0 + 1.0

    def test_calculate_sheet_layout_item_does_not_fit(self) -> None:
        layout = calculate_sheet_layout(
            item_width_inches=20.0,
            item_height_inches=20.0,
            sheet_width_inches=8.5,
            sheet_height_inches=11.0,
        )
        self.assertFalse(layout["fits"])
        self.assertEqual(layout["capacity"], 0)
        self.assertEqual(layout["placements"], [])

    def test_calculate_sheet_layout_truncation(self) -> None:
        # High capacity layout exceeding MAX_LAYOUT_PLACEMENTS (2000)
        layout = calculate_sheet_layout(
            item_width_inches=0.1,
            item_height_inches=0.1,
            sheet_width_inches=50.0,
            sheet_height_inches=50.0,
        )
        self.assertGreater(layout["capacity"], MAX_LAYOUT_PLACEMENTS)
        self.assertTrue(layout["placements_truncated"])
        self.assertEqual(layout["placements_limit"], MAX_LAYOUT_PLACEMENTS)
        self.assertEqual(len(layout["placements"]), MAX_LAYOUT_PLACEMENTS)

    def test_best_fit_evaluates_mixed_rows_and_columns(self) -> None:
        layout = calculate_sheet_layout(
            5.0, 2.0, 9.0, 14.0,
            rotation_policy="best_fit",
            requested_quantity=100,
        )

        self.assertEqual(layout["layout_strategy"], "mixed_rotated_columns")
        self.assertEqual(layout["capacity"], 11)
        self.assertTrue(layout["mixed_rotation"])
        self.assertEqual(layout["sheets_required"], 10)
        self.assertEqual(layout["total_produced"], 110)
        self.assertEqual(layout["overage"], 10)
        capacities = {
            item["layout_strategy"]: item["capacity"]
            for item in layout["alternatives"]
        }
        self.assertEqual(capacities["upright_grid"], 7)
        self.assertEqual(capacities["rotated_grid"], 8)
        self.assertEqual(capacities["mixed_rotated_rows"], 10)
        self.assertEqual(capacities["mixed_rotated_columns"], 11)
        self.assertEqual(sum(not item["rotated"] for item in layout["placements"]), 7)
        self.assertEqual(sum(item["rotated"] for item in layout["placements"]), 4)

    def test_best_fit_placements_stay_in_bounds_and_do_not_overlap(self) -> None:
        layout = calculate_sheet_layout(
            5.0, 2.0, 9.5, 14.5,
            margin_inches=0.25,
            gutter_inches=0.125,
            rotation_policy="best_fit",
        )

        placements = layout["placements"]
        margins = layout["margins_inches"]
        for item in placements:
            self.assertGreaterEqual(item["x_inches"], margins["left"] - 1e-6)
            self.assertGreaterEqual(item["y_inches"], margins["bottom"] - 1e-6)
            self.assertLessEqual(item["x_inches"] + item["width_inches"], layout["sheet_width_inches"] - margins["right"] + 1e-6)
            self.assertLessEqual(item["y_inches"] + item["height_inches"], layout["sheet_height_inches"] - margins["top"] + 1e-6)
        for index, first in enumerate(placements):
            for second in placements[index + 1:]:
                separated = (
                    first["x_inches"] + first["width_inches"] <= second["x_inches"] + 1e-6
                    or second["x_inches"] + second["width_inches"] <= first["x_inches"] + 1e-6
                    or first["y_inches"] + first["height_inches"] <= second["y_inches"] + 1e-6
                    or second["y_inches"] + second["height_inches"] <= first["y_inches"] + 1e-6
                )
                self.assertTrue(separated)

    def test_orientation_and_allowance_policies_are_exact(self) -> None:
        layout = calculate_sheet_layout(
            3.0, 4.0, 12.0, 8.0,
            rotation_policy="never",
            sheet_orientation="best_fit",
            margin_left_inches=0.25,
            margin_right_inches=0.25,
            margin_top_inches=0.25,
            margin_bottom_inches=0.25,
            gripper_inches=0.5,
            gripper_edge="bottom",
            mark_clearance_inches=0.125,
        )

        self.assertEqual(layout["sheet_orientation"], "portrait")
        self.assertTrue(layout["sheet_orientation_changed"])
        self.assertEqual(layout["margins_inches"]["bottom"], 0.875)
        self.assertEqual(layout["margins_inches"]["top"], 0.375)
        self.assertEqual(layout["rotation_policy"], "never")
        self.assertFalse(layout["rotation_used"])

    def test_calculate_sheet_layout_invalid_arguments(self) -> None:
        invalid_cases = [
            (-1.0, 2.0, 10.0, 10.0, 0.0, 0.0, True),
            (2.0, 0.0, 10.0, 10.0, 0.0, 0.0, True),
            (2.0, 2.0, -10.0, 10.0, 0.0, 0.0, True),
            (2.0, 2.0, 10.0, 10.0, -1.0, 0.0, True),
            (2.0, 2.0, 10.0, 10.0, 0.0, -0.5, True),
            (float("nan"), 2.0, 10.0, 10.0, 0.0, 0.0, True),
            (2.0, 2.0, 10.0, 10.0, 0.0, 0.0, "not_bool"),
            (True, 2.0, 10.0, 10.0, 0.0, 0.0, True),
        ]
        for item_w, item_h, sheet_w, sheet_h, margin, gutter, rotate in invalid_cases:
            with self.subTest(item_w=item_w, item_h=item_h, sheet_w=sheet_w, sheet_h=sheet_h):
                with self.assertRaises(CorelBridgeError) as ctx:
                    calculate_sheet_layout(
                        item_w, item_h, sheet_w, sheet_h, margin, gutter, rotate  # type: ignore
                    )
                self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_build_chest_number_sequence_pure_sequence(self) -> None:
        result = build_chest_number_sequence(start=1, end=5, zero_pad_width=3)
        self.assertEqual(result["count"], 5)
        self.assertTrue(result["sequence_valid"])
        self.assertFalse(result["layout_checked"])
        self.assertFalse(result["fits_sheet"])
        self.assertIsNone(result["layout"])
        labels = [item["label"] for item in result["items"]]
        names = [item["object_name"] for item in result["items"]]
        self.assertEqual(labels, ["001", "002", "003", "004", "005"])
        self.assertEqual(names, [
            "chest_number_001",
            "chest_number_002",
            "chest_number_003",
            "chest_number_004",
            "chest_number_005",
        ])

    def test_build_chest_number_sequence_without_zero_padding(self) -> None:
        result = build_chest_number_sequence(start=98, end=100, zero_pad_width=0)
        self.assertEqual(result["count"], 3)
        self.assertTrue(result["sequence_valid"])
        labels = [item["label"] for item in result["items"]]
        names = [item["object_name"] for item in result["items"]]
        self.assertEqual(labels, ["98", "99", "100"])
        self.assertEqual(names, ["chest_number_98", "chest_number_99", "chest_number_100"])

    def test_build_chest_number_sequence_with_layout(self) -> None:
        result = build_chest_number_sequence(
            start=1,
            end=4,
            zero_pad_width=2,
            item_width_inches=3.0,
            item_height_inches=2.0,
            sheet_width_inches=8.0,
            sheet_height_inches=6.0,
            margin_inches=0.5,
        )
        self.assertEqual(result["count"], 4)
        self.assertTrue(result["sequence_valid"])
        self.assertTrue(result["layout_checked"])
        self.assertTrue(result["fits_sheet"])
        self.assertIsNotNone(result["layout"])
        self.assertIn("placements", result["layout"])
        for item in result["items"]:
            self.assertIn("placement", item)
            self.assertIn("x_inches", item["placement"])
            self.assertIn("y_inches", item["placement"])

    def test_build_chest_number_sequence_capacity_exceeded(self) -> None:
        # Sheet only fits 2 items, but we request 5 items
        result = build_chest_number_sequence(
            start=1,
            end=5,
            item_width_inches=5.0,
            item_height_inches=5.0,
            sheet_width_inches=8.0,
            sheet_height_inches=6.0,
        )
        self.assertEqual(result["count"], 5)
        self.assertTrue(result["sequence_valid"])
        self.assertTrue(result["layout_checked"])
        self.assertFalse(result["fits_sheet"])
        self.assertIsNotNone(result["layout"])
        self.assertLess(result["layout"]["capacity"], 5)
        # Placements should not be bound to items if sheet cannot fit all
        self.assertNotIn("placement", result["items"][0])

    def test_build_chest_number_sequence_validation_errors(self) -> None:
        # Negative start
        with self.assertRaises(CorelBridgeError) as ctx:
            build_chest_number_sequence(start=-1, end=10)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

        # End before start
        with self.assertRaises(CorelBridgeError) as ctx:
            build_chest_number_sequence(start=10, end=5)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

        # Exceeds maximum sequence limit
        with self.assertRaises(CorelBridgeError) as ctx:
            build_chest_number_sequence(start=1, end=MAX_CHEST_NUMBER_SEQUENCE + 2)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

        # Partial layout inputs
        with self.assertRaises(CorelBridgeError) as ctx:
            build_chest_number_sequence(start=1, end=5, item_width_inches=3.0)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

        # Non-integer / boolean inputs
        with self.assertRaises(CorelBridgeError) as ctx:
            build_chest_number_sequence(start=True, end=10)  # type: ignore
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

        # Margin specified without layout dimensions
        with self.assertRaises(CorelBridgeError) as ctx:
            build_chest_number_sequence(start=1, end=5, margin_inches=0.5)
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)


class _MockShape:
    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.Name = ""
        self.PositionX = x
        self.PositionY = y
        self.SizeWidth = w
        self.SizeHeight = h

    def SetPosition(self, x: float, y: float) -> None:
        self.PositionX = x
        self.PositionY = y


class _MockLayer:
    def __init__(self, shapes: list[_MockShape]) -> None:
        self.shapes = shapes

    def CreateRectangle2(self, x, y, width, height):
        shape = _MockShape(x, y, width, height)
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
        self.Name = "TestBatchDoc"
        self.Unit = 1
        self.ReferencePoint = 5
        self.ActivePage = _MockPage(width, height)


class CreateChestNumberBatchBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        from corel_operator.corel_bridge import CorelBridge
        self.bridge = CorelBridge()
        self.doc = _MockDocument(8.5, 11.0)
        attach_open_document(self.bridge, self.doc)

    def test_create_chest_number_batch_success(self) -> None:
        result = self.bridge.create_chest_number_batch(
            start=1,
            end=4,
            item_width_inches=3.0,
            item_height_inches=2.0,
            zero_pad_width=3,
            draw_border=True,
        )
        self.assertTrue(result["created"])
        self.assertEqual(result["created_count"], 4)
        self.assertEqual(result["count"], 4)
        self.assertEqual(len(result["items"]), 4)
        self.assertEqual(len(result["object_names"]), 8)  # 4 boxes + 4 numbers
        self.assertIn("chest_number_001_box", result["object_names"])
        self.assertIn("chest_number_001_number", result["object_names"])

    def test_create_chest_number_batch_with_header_and_footer(self) -> None:
        result = self.bridge.create_chest_number_batch(
            start=10,
            end=11,
            item_width_inches=3.0,
            item_height_inches=2.0,
            zero_pad_width=0,
            header_text="SUMMER RACE",
            footer_text="5K RUN",
            draw_border=True,
        )
        self.assertEqual(result["created_count"], 2)
        # 2 items * 4 shapes each (box, header, number, footer) = 8 shapes
        self.assertEqual(len(result["object_names"]), 8)
        self.assertIn("chest_number_10_header", result["object_names"])
        self.assertIn("chest_number_10_footer", result["object_names"])
        self.assertIn("chest_number_10_number", result["object_names"])
        self.assertIn("chest_number_10_box", result["object_names"])

    def test_create_chest_number_batch_capacity_error(self) -> None:
        # 6x6 items on 8.5x11: only 1 column and 1 row fits (capacity 1), requesting 4 items
        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.create_chest_number_batch(
                start=1,
                end=4,
                item_width_inches=6.0,
                item_height_inches=6.0,
            )
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_create_chest_number_batch_no_target_document(self) -> None:
        self.bridge.target_doc = None
        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.create_chest_number_batch(
                start=1,
                end=2,
                item_width_inches=3.0,
                item_height_inches=2.0,
            )
        self.assertEqual(ctx.exception.code, ErrorCode.NO_TARGET_DOCUMENT)

    def test_create_chest_number_batch_font_validation(self) -> None:
        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.create_chest_number_batch(
                start=1,
                end=2,
                item_width_inches=3.0,
                item_height_inches=2.0,
                font="",
            )
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as ctx:
            self.bridge.create_chest_number_batch(
                start=1,
                end=2,
                item_width_inches=3.0,
                item_height_inches=2.0,
                font_size_points=0,
            )
        self.assertEqual(ctx.exception.code, ErrorCode.INVALID_ARGUMENT)


if __name__ == "__main__":
    unittest.main()
