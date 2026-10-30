from __future__ import annotations

import unittest

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


class BridgeErrorCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = CorelBridge()

    def assert_error_code(self, expected: ErrorCode, function, *args, **kwargs) -> None:
        with self.assertRaises(CorelBridgeError) as context:
            function(*args, **kwargs)
        self.assertEqual(context.exception.code, expected)

    def test_missing_target(self) -> None:
        self.assert_error_code(ErrorCode.NO_TARGET_DOCUMENT, self.bridge._target_document)

    def test_existing_document_requires_confirmation(self) -> None:
        self.assert_error_code(
            ErrorCode.CONFIRMATION_REQUIRED,
            self.bridge.use_active_document,
            False,
        )

    def test_empty_text_is_invalid_before_com_access(self) -> None:
        self.assert_error_code(
            ErrorCode.INVALID_ARGUMENT,
            self.bridge.add_text,
            " ",
            1,
            1,
        )

    def test_invalid_page_size_is_rejected_before_com_access(self) -> None:
        self.bridge._require_app = lambda: self.fail("COM access must not occur")
        self.assert_error_code(
            ErrorCode.INVALID_ARGUMENT,
            self.bridge.create_document,
            0,
            11,
        )

    def test_invalid_rectangle_is_rejected_before_com_access(self) -> None:
        self.assert_error_code(
            ErrorCode.INVALID_ARGUMENT,
            self.bridge.draw_rectangle,
            0,
            0,
            0,
            1,
        )

    def test_invalid_rgb(self) -> None:
        self.assert_error_code(
            ErrorCode.INVALID_ARGUMENT,
            self.bridge._validate_rgb,
            256,
            0,
            0,
        )

    def test_ambiguous_selector(self) -> None:
        self.assert_error_code(
            ErrorCode.AMBIGUOUS_SELECTOR,
            self.bridge._find_shape,
            object(),
            "",
            0,
        )

    def test_nonexistent_import_path_is_unsafe(self) -> None:
        self.assert_error_code(
            ErrorCode.UNSAFE_PATH,
            self.bridge.import_artwork,
            "Z:/this/path/does/not/exist.svg",
        )


if __name__ == "__main__":
    unittest.main()
