from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


TEMP_ROOT = Path(tempfile.gettempdir()) / "opencode"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class PathSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = CorelBridge()
        self.bridge.target_doc = object()

    def assert_code(self, expected: ErrorCode, function, *args) -> None:
        with self.assertRaises(CorelBridgeError) as context:
            function(*args)
        self.assertEqual(context.exception.code, expected)

    def test_missing_import_is_unsafe_path(self) -> None:
        self.assert_code(
            ErrorCode.UNSAFE_PATH,
            self.bridge.import_artwork,
            str(TEMP_ROOT / "missing.svg"),
        )

    def test_disallowed_import_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "script.exe"
            path.write_bytes(b"not executable")
            self.assert_code(ErrorCode.INVALID_ARGUMENT, self.bridge.import_artwork, str(path))

    def test_import_size_limit_is_checked_before_com_access(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "image.png"
            path.write_bytes(b"12")
            self.bridge.MAX_IMPORT_BYTES = 1
            self.assert_code(ErrorCode.INVALID_ARGUMENT, self.bridge.import_artwork, str(path))

    def test_save_requires_cdr_extension(self) -> None:
        self.assert_code(
            ErrorCode.INVALID_ARGUMENT,
            self.bridge.save_document,
            str(TEMP_ROOT / "output.txt"),
        )

    def test_save_refuses_existing_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "existing.cdr"
            path.write_bytes(b"existing")
            self.assert_code(ErrorCode.OUTPUT_EXISTS, self.bridge.save_document, str(path))
            self.assertEqual(path.read_bytes(), b"existing")

    def test_pdf_export_refuses_existing_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "existing.pdf"
            path.write_bytes(b"existing")
            self.assert_code(ErrorCode.OUTPUT_EXISTS, self.bridge.export_pdf, str(path))
            self.assertEqual(path.read_bytes(), b"existing")

    def test_expanduser_and_absolute_path_do_not_change_extension_policy(self) -> None:
        path = os.path.join("~", "unsafe.exe")
        self.assert_code(ErrorCode.UNSAFE_PATH, self.bridge.import_artwork, path)


if __name__ == "__main__":
    unittest.main()
