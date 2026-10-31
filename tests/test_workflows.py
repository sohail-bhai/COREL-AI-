from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
