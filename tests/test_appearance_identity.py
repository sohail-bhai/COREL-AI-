from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from corel_operator.corel_bridge import CorelBridge
from fake_documents import attach_open_document


TEMP_ROOT = Path(tempfile.gettempdir()) / "opencode"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class _Color:
    Type = 5
    Name = "RGB Color"

    def __init__(self, red: int, green: int, blue: int) -> None:
        self.RGBRed = red
        self.RGBGreen = green
        self.RGBBlue = blue
        self.HexValue = f"{red:02X}{green:02X}{blue:02X}"


class _Fill:
    def __init__(self) -> None:
        self.Type = 0
        self.UniformColor = None

    def ApplyUniformFill(self, color: _Color) -> None:
        self.Type = 1
        self.UniformColor = color


class _Outline:
    def __init__(self) -> None:
        self.Type = 1
        self.Color = _Color(0, 0, 0)
        self.Width = 0.5

    def SetNoOutline(self) -> None:
        self.Type = 0


class _ShapeRange:
    def __init__(self, items=None) -> None:
        self.items = list(items or [])

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _Shape:
    def __init__(self, static_id: int, layer, page, owner) -> None:
        self.Name = ""
        self.StaticID = static_id
        self.Type = 1
        self.Layer = layer
        self.Page = page
        self.owner = owner
        self.PositionX = 1.0
        self.PositionY = 2.0
        self.SizeWidth = 3.0
        self.SizeHeight = 4.0
        self.Fill = _Fill()
        self.Outline = _Outline()

    def Duplicate(self, offset_x: float, offset_y: float):
        duplicate = _Shape(self.StaticID + 1000, self.Layer, self.Page, self.owner)
        duplicate.PositionX = self.PositionX + offset_x
        duplicate.PositionY = self.PositionY + offset_y
        duplicate.SizeWidth = self.SizeWidth
        duplicate.SizeHeight = self.SizeHeight
        self.owner.items.append(duplicate)
        return duplicate


class _Layer:
    Name = "Layer 1"

    def __init__(self) -> None:
        self.page = None
        self.document = None

    def Import(self, file_path: str) -> None:
        shape = self.page.create_shape(900)
        self.document.SelectionRange = _ShapeRange([shape])


class _Page:
    Index = 1

    def __init__(self, layer: _Layer) -> None:
        self.Shapes = _ShapeRange()
        self.ActiveLayer = layer
        layer.page = self

    def create_shape(self, static_id: int) -> _Shape:
        shape = _Shape(static_id, self.ActiveLayer, self, self.Shapes)
        self.Shapes.items.append(shape)
        return shape


class _Document:
    Name = "Graphic1"

    def __init__(self) -> None:
        self.Unit = 1
        self.ReferencePoint = 5
        self.layer = _Layer()
        self.ActivePage = _Page(self.layer)
        self.layer.document = self
        self.SelectionRange = _ShapeRange()

    def ClearSelection(self) -> None:
        self.SelectionRange = _ShapeRange()


class _Application:
    @staticmethod
    def CreateRGBColor(red: int, green: int, blue: int) -> _Color:
        return _Color(red, green, blue)


class AppearanceAndIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = _Document()
        self.shape = self.document.ActivePage.create_shape(101)
        self.shape.Name = "panel"
        self.bridge = CorelBridge()
        self.bridge.app = _Application()
        attach_open_document(self.bridge, self.document)

    def test_fill_update_returns_native_rgb_readback(self) -> None:
        result = self.bridge.set_fill_color(20, 45, 90, object_name="panel")

        self.assertEqual(result["actual_fill"]["type"], "uniform")
        self.assertEqual(result["actual_fill"]["color"]["model"], "rgb")
        self.assertEqual(
            result["actual_fill"]["color"]["value"],
            {"red": 20, "green": 45, "blue": 90},
        )

    def test_outline_update_labels_width_units_as_unverified(self) -> None:
        result = self.bridge.set_outline(255, 0, 0, 2.0, object_name="panel")

        actual = result["actual_outline"]
        self.assertTrue(actual["present"])
        self.assertEqual(actual["type"], "outline")
        self.assertAlmostEqual(actual["width_raw"], 2.0 / 72.0, places=4)
        self.assertEqual(actual["width_units"], "coreldraw_outline_width_unverified")
        self.assertEqual(actual["color"]["value"], {"red": 255, "green": 0, "blue": 0})

    def test_outline_removal_is_read_back(self) -> None:
        result = self.bridge.set_outline(0, 0, 0, 0, object_name="panel")
        self.assertTrue(result["outline_removed"])
        self.assertFalse(result["actual_outline"]["present"])
        self.assertEqual(result["actual_outline"]["type"], "none")

    def test_object_listing_includes_static_identity_and_appearance(self) -> None:
        self.bridge.set_fill_color(1, 2, 3, object_name="panel")
        result = self.bridge.list_objects()
        listed = result["objects"][0]

        self.assertEqual(listed["static_id"], 101)
        self.assertEqual(listed["layer_name"], "Layer 1")
        self.assertEqual(listed["page_index"], 1)
        self.assertEqual(listed["fill"]["color"]["value"], {"red": 1, "green": 2, "blue": 3})
        self.assertIn("unverified COM units", result["warning"])

    def test_rename_and_duplicate_return_identity(self) -> None:
        renamed = self.bridge.rename_object("primary_panel", object_name="panel")
        self.assertEqual(renamed["object"]["static_id"], 101)

        duplicated = self.bridge.duplicate_object(
            object_name="primary_panel",
            new_name="panel_copy",
        )
        self.assertEqual(duplicated["object"]["object_name"], "panel_copy")
        self.assertEqual(duplicated["object"]["static_id"], 1101)

    def test_import_returns_identity_for_each_imported_object(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "logo.svg"
            path.write_text("<svg/>", encoding="utf-8")

            result = self.bridge.import_artwork(str(path), "logo")

        self.assertEqual(result["object_count"], 1)
        self.assertEqual(result["object_names"], ["logo"])
        self.assertEqual(result["objects"][0]["static_id"], 900)
        self.assertEqual(result["objects"][0]["layer_name"], "Layer 1")
        self.assertEqual(result["objects"][0]["page_index"], 1)


if __name__ == "__main__":
    unittest.main()
