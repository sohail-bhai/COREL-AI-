from __future__ import annotations

import unittest

from corel_operator.corel_bridge import CorelBridge


class _FakeDocument:
    def __init__(self, unit: int = 3, reference_point: int = 9) -> None:
        self.Unit = unit
        self.ReferencePoint = reference_point


class UnitContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = CorelBridge()

    def test_inch_enum_matches_x7_type_library_value(self) -> None:
        self.assertEqual(self.bridge.CDR_INCH, 1)

    def test_inch_context_sets_and_restores_document_unit(self) -> None:
        document = _FakeDocument(unit=3)

        with self.bridge._in_inches(document):
            self.assertEqual(document.Unit, 1)

        self.assertEqual(document.Unit, 3)

    def test_inch_context_restores_after_exception(self) -> None:
        document = _FakeDocument(unit=4)

        with self.assertRaisesRegex(RuntimeError, "test"):
            with self.bridge._in_inches(document):
                self.assertEqual(document.Unit, 1)
                raise RuntimeError("test")

        self.assertEqual(document.Unit, 4)

    def test_inch_context_does_not_reassign_existing_inch_unit(self) -> None:
        document = _FakeDocument(unit=1)
        with self.bridge._in_inches(document):
            self.assertEqual(document.Unit, 1)
        self.assertEqual(document.Unit, 1)

    def test_reference_point_context_sets_and_restores_bottom_left(self) -> None:
        document = _FakeDocument(reference_point=9)

        with self.bridge._reference_point(document):
            self.assertEqual(document.ReferencePoint, 5)

        self.assertEqual(document.ReferencePoint, 9)


if __name__ == "__main__":
    unittest.main()
