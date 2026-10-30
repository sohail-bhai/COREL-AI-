from __future__ import annotations

import unittest

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


class _Collection:
    def __init__(self, items=None) -> None:
        self.items = list(items or [])

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _Color:
    Type = 5
    HexValue = "0A141E"
    Name = "RGB Color"
    RGBRed = 10
    RGBGreen = 20
    RGBBlue = 30


class _Fill:
    Type = 1
    UniformColor = _Color()


class _Outline:
    Type = 1
    Width = 0.5
    Color = _Color()


class _Story:
    Text = "Inspection text"
    Font = "Arial"
    Size = 18.0
    Bold = -1


class _Text:
    Story = _Story()


class _Shape:
    def __init__(self, name: str, static_id: int) -> None:
        self.Name = name
        self.StaticID = static_id
        self.Type = 6
        self.PositionX = 1.25
        self.PositionY = 2.5
        self.SizeWidth = 3.0
        self.SizeHeight = 0.5
        self.Text = _Text()
        self.Fill = _Fill()
        self.Outline = _Outline()
        self.Layer = None
        self.Page = None


class _Layer:
    def __init__(self, name: str, index: int, shapes=None, master: bool = False) -> None:
        self.Name = name
        self.Index = index
        self.AbsoluteIndex = index
        self.Visible = True
        self.Editable = True
        self.Printable = True
        self.Master = master
        self.IsSpecialLayer = master
        self.Shapes = _Collection(shapes)


class _Page:
    def __init__(self, index: int, name: str, width: float, height: float, layers) -> None:
        self.Index = index
        self.Name = name
        self.Orientation = 0 if width <= height else 1
        self.SizeWidth = width
        self.SizeHeight = height
        self.AllLayers = _Collection(layers)
        self.Layers = self.AllLayers
        self.ActiveLayer = layers[0]
        shapes = []
        for layer in layers:
            shapes.extend(layer.Shapes.items)
            for shape in layer.Shapes.items:
                shape.Layer = layer
                shape.Page = self
        self.Shapes = _Collection(shapes)

    def GetSize(self):
        return self.SizeWidth, self.SizeHeight


class _Document:
    def __init__(self, name: str, path: str, pages, dirty: bool = False) -> None:
        self.Name = name
        self.FullFileName = path
        self.Dirty = dirty
        self.Unit = 1
        self.ReferencePoint = 5
        self.Pages = _Collection(pages)
        self.ActivePage = pages[0]


class _Application:
    def __init__(self, documents, active_document) -> None:
        self.Documents = _Collection(documents)
        self.ActiveDocument = active_document


class InspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text_shape = _Shape("headline", 101)
        page_layer = _Layer("Layer 1", 1, [self.text_shape])
        master_layer = _Layer("Guides", 2, [], master=True)
        page_1 = _Page(1, "Front", 8.5, 11.0, [page_layer, master_layer])
        page_2 = _Page(2, "Back", 11.0, 8.5, [_Layer("Layer 1", 1)])
        self.target = _Document("Target.cdr", r"C:\jobs\Target.cdr", [page_1, page_2], dirty=True)
        self.other = _Document("Graphic1", "", [_Page(1, "Page 1", 8.0, 10.0, [_Layer("Layer 1", 1)])])
        self.app = _Application([self.target, self.other], self.other)
        self.bridge = CorelBridge()
        self.bridge.app = self.app
        self.bridge.target_doc = self.target

    def test_list_open_documents_has_stable_process_local_identity(self) -> None:
        first = self.bridge.list_open_documents()["documents"]
        second = self.bridge.list_open_documents()["documents"]

        self.assertEqual(first[0]["session_id"], second[0]["session_id"])
        self.assertNotEqual(first[0]["session_id"], first[1]["session_id"])
        self.assertTrue(first[0]["is_bound_target"])
        self.assertFalse(first[0]["is_active"])
        self.assertTrue(first[1]["is_active"])
        self.assertFalse(first[1]["saved"])
        self.assertIs(self.app.ActiveDocument, self.other)

    def test_get_document_info_reports_bound_target_not_active_document(self) -> None:
        result = self.bridge.get_document_info()["document"]

        self.assertEqual(result["name"], "Target.cdr")
        self.assertTrue(result["dirty"])
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["active_page_index"], 1)
        self.assertTrue(result["is_bound_target"])
        self.assertFalse(result["is_active"])

    def test_list_pages_reads_all_pages_without_changing_active_page_or_unit(self) -> None:
        original_page = self.target.ActivePage
        result = self.bridge.list_pages()["pages"]

        self.assertEqual([page["name"] for page in result], ["Front", "Back"])
        self.assertEqual(result[0]["width_inches"], 8.5)
        self.assertEqual(result[1]["height_inches"], 8.5)
        self.assertTrue(result[0]["is_active"])
        self.assertIs(self.target.ActivePage, original_page)
        self.assertEqual(self.target.Unit, 1)

    def test_get_page_bounds_uses_explicit_page_local_coordinate_space(self) -> None:
        result = self.bridge.get_page_bounds(2)

        self.assertEqual(result["unit"], "inch")
        self.assertEqual(result["bounds"]["lower_left"], {"x": 0.0, "y": 0.0})
        self.assertEqual(result["bounds"]["upper_right"], {"x": 11.0, "y": 8.5})
        self.assertEqual(result["bounds"]["center"], {"x": 5.5, "y": 4.25})
        self.assertEqual(result["bounds"]["coordinate_space"], "page_local_bottom_left")

    def test_page_index_errors_are_stable(self) -> None:
        with self.assertRaises(CorelBridgeError) as caught:
            self.bridge.get_page_bounds(3)
        self.assertEqual(caught.exception.code, ErrorCode.OBJECT_NOT_FOUND)
        self.assertEqual(caught.exception.details["page_count"], 2)

    def test_list_layers_reports_state_without_changing_active_layer(self) -> None:
        original_layer = self.target.ActivePage.ActiveLayer
        result = self.bridge.list_layers(1)

        self.assertEqual(result["page_index"], 1)
        self.assertEqual([layer["name"] for layer in result["layers"]], ["Layer 1", "Guides"])
        self.assertEqual(result["layers"][0]["object_count"], 1)
        self.assertTrue(result["layers"][0]["is_active"])
        self.assertTrue(result["layers"][1]["master"])
        self.assertIs(self.target.ActivePage.ActiveLayer, original_layer)

    def test_get_object_info_combines_identity_geometry_text_and_appearance(self) -> None:
        result = self.bridge.get_object_info(object_name="headline")["object"]

        self.assertEqual(result["object_id"], "doc-0001:shape:101")
        self.assertEqual(result["document_session_id"], "doc-0001")
        self.assertEqual(result["shape_index"], 1)
        self.assertEqual(result["layer_name"], "Layer 1")
        self.assertEqual(result["page_index"], 1)
        self.assertEqual(result["bounds_inches"]["width"], 3.0)
        self.assertEqual(result["text"]["text"], "Inspection text")
        self.assertEqual(result["fill"]["color"]["value"], {"red": 10, "green": 20, "blue": 30})
        self.assertTrue(result["outline"]["present"])


if __name__ == "__main__":
    unittest.main()
