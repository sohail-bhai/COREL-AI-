from __future__ import annotations

import tempfile
import unittest

from fake_documents import attach_open_document
from pathlib import Path

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


TEMP_ROOT = Path(tempfile.gettempdir()) / "opencode"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class _Shapes:
    def __init__(self) -> None:
        self.items: list[_Shape] = []

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _Story:
    def __init__(self, text: str, font: str, size: float, bold: int) -> None:
        self.Text = text
        self.Font = font
        self.Size = size
        self.Bold = bold


class _Text:
    def __init__(self, story: _Story) -> None:
        self.Story = story


class _Shape:
    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.Name = ""
        self.PositionX = x
        self.PositionY = y
        self.SizeWidth = width
        self.SizeHeight = height


class _Layer:
    def __init__(self, shapes: _Shapes) -> None:
        self.shapes = shapes

    def CreateRectangle2(self, x, y, width, height):
        shape = _Shape(x, y, width, height)
        self.shapes.items.append(shape)
        return shape

    def CreateEllipse2(self, center_x, center_y, radius_1, radius_2, *args):
        shape = _Shape(
            center_x - radius_1,
            center_y - radius_2,
            radius_1 * 2,
            radius_2 * 2,
        )
        self.shapes.items.append(shape)
        return shape

    def CreateArtisticText(
        self,
        left,
        bottom,
        text,
        language_id,
        charset,
        font,
        size,
        bold,
    ):
        shape = _Shape(left, bottom, 3.25, 0.4)
        shape.Text = _Text(_Story(text, font, size, bold))
        self.shapes.items.append(shape)
        return shape


class _Page:
    def __init__(self) -> None:
        self.Shapes = _Shapes()
        self.ActiveLayer = _Layer(self.Shapes)


class _Document:
    def __init__(self) -> None:
        self.Name = "Graphic1"
        self.Unit = 3
        self.ReferencePoint = 9
        self.ActivePage = _Page()


class _PublishingDocument:
    Name = "Graphic1"

    def __init__(self, content: bytes | None) -> None:
        self.content = content

    def PublishToPDF(self, path: str) -> None:
        if self.content is not None:
            Path(path).write_bytes(self.content)


class ActualReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = CorelBridge()
        self.document = _Document()
        attach_open_document(self.bridge, self.document)

    def test_rectangle_returns_actual_bounds_and_restores_document_state(self) -> None:
        result = self.bridge.draw_rectangle(1, 2, 3, 4, "panel")

        self.assertEqual(
            result["actual_bounds_inches"],
            {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0},
        )
        self.assertEqual(self.document.Unit, 3)
        self.assertEqual(self.document.ReferencePoint, 9)

    def test_ellipse_returns_requested_bounding_box_after_center_conversion(self) -> None:
        result = self.bridge.draw_ellipse(1, 2, 4, 2, "badge")

        self.assertEqual(
            result["actual_bounds_inches"],
            {"x": 1.0, "y": 2.0, "width": 4.0, "height": 2.0},
        )

    def test_artistic_text_returns_actual_content_format_and_bounds(self) -> None:
        result = self.bridge.add_text("TITLE", 1.2, 8.5, 22, "Arial", True, "title")

        self.assertEqual(
            result["actual_text"],
            {
                "text": "TITLE",
                "font": "Arial",
                "size_points": 22.0,
                "bold": True,
                "bold_code": -1,
            },
        )
        self.assertEqual(
            result["actual_bounds_inches"],
            {"x": 1.2, "y": 8.5, "width": 3.25, "height": 0.4},
        )

    def test_pdf_export_verifies_nonempty_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "preview.pdf"
            attach_open_document(self.bridge, _PublishingDocument(b"%PDF-test"))

            result = self.bridge.export_pdf(str(path))

            self.assertTrue(result["exported"])
            self.assertEqual(result["bytes"], len(b"%PDF-test"))
            self.assertEqual(path.read_bytes(), b"%PDF-test")

    def test_pdf_export_rejects_missing_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "missing.pdf"
            attach_open_document(self.bridge, _PublishingDocument(None))

            with self.assertRaises(CorelBridgeError) as context:
                self.bridge.export_pdf(str(path))

            self.assertEqual(context.exception.code, ErrorCode.COREL_COM_ERROR)
            self.assertFalse(path.exists())

    def test_pdf_export_rejects_empty_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "empty.pdf"
            attach_open_document(self.bridge, _PublishingDocument(b""))

            with self.assertRaises(CorelBridgeError) as context:
                self.bridge.export_pdf(str(path))

            self.assertEqual(context.exception.code, ErrorCode.COREL_COM_ERROR)
            self.assertEqual(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
