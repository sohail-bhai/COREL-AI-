from __future__ import annotations

import math
import unittest

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


class InputValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = CorelBridge()

    def assert_invalid(self, function, *args, **kwargs) -> None:
        with self.assertRaises(CorelBridgeError) as context:
            function(*args, **kwargs)
        self.assertEqual(context.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_page_dimensions_reject_zero_negative_large_and_nan(self) -> None:
        self.assert_invalid(self.bridge.create_document, 0, 11)
        self.assert_invalid(self.bridge.create_document, -1, 11)
        self.assert_invalid(self.bridge.create_document, 201, 11)
        self.assert_invalid(self.bridge.create_document, math.nan, 11)

    def test_font_size_bounds(self) -> None:
        self.assert_invalid(self.bridge.add_text, "Title", 1, 1, 0)
        self.assert_invalid(self.bridge.add_text, "Title", 1, 1, 501)

    def test_shape_dimensions_must_be_positive(self) -> None:
        self.assert_invalid(self.bridge.draw_rectangle, 0, 0, 1, 0)
        self.assert_invalid(self.bridge.draw_ellipse, 0, 0, -1, 1)

    def test_object_list_limit(self) -> None:
        self.assert_invalid(self.bridge.list_objects, 0)
        self.assert_invalid(self.bridge.list_objects, 1001)

    def test_rgb_rejects_booleans_floats_and_out_of_range_values(self) -> None:
        self.assert_invalid(self.bridge._validate_rgb, True, 0, 0)
        self.assert_invalid(self.bridge._validate_rgb, 1.0, 0, 0)
        self.assert_invalid(self.bridge._validate_rgb, -1, 0, 0)
        self.assert_invalid(self.bridge._validate_rgb, 256, 0, 0)

    def test_outline_width_bounds_are_checked_before_target_access(self) -> None:
        self.assert_invalid(self.bridge.set_outline, 0, 0, 0, -0.1, "shape", 0)
        self.assert_invalid(self.bridge.set_outline, 0, 0, 0, 72.1, "shape", 0)
        self.assert_invalid(self.bridge.set_outline, 0, 0, 0, math.nan, "shape", 0)

    def test_resize_requires_sufficient_dimensions(self) -> None:
        self.assert_invalid(self.bridge.resize_object, 0, 0, False, "shape", 0)
        self.assert_invalid(self.bridge.resize_object, 1, 0, False, "shape", 0)

    def test_blank_text_and_names_are_rejected(self) -> None:
        self.assert_invalid(self.bridge.set_text_content, " ", "shape", 0)
        self.assert_invalid(self.bridge.rename_object, " ", "shape", 0)


if __name__ == "__main__":
    unittest.main()
