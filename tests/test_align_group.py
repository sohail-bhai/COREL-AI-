from __future__ import annotations

import unittest
from typing import Any

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode


class _MockShape:
    def __init__(self, name: str, x: float, y: float, w: float, h: float, shape_type: int = 1) -> None:
        self.Name = name
        self.PositionX = x
        self.PositionY = y
        self.SizeWidth = w
        self.SizeHeight = h
        self.Type = shape_type
        self.child_shapes: list[_MockShape] = []
        self.ungroup_called = 0
        self.ungroup_all_called = 0

    @property
    def Shapes(self):
        return _MockShapesCollection(self.child_shapes)

    def Ungroup(self):
        self.ungroup_called += 1

    def UngroupAll(self):
        self.ungroup_all_called += 1


class _MockShapesCollection:
    def __init__(self, shapes: list[_MockShape]) -> None:
        self.items = shapes

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _MockShapeRange:
    def __init__(self, doc: _MockDocument) -> None:
        self.doc = doc
        self.shapes: list[_MockShape] = []
        self.align_and_distribute_calls: list[dict[str, Any]] = []
        self.align_range_to_page_calls: list[int] = []
        self.align_range_to_page_center_calls: list[int] = []

    def Add(self, shape: _MockShape) -> None:
        self.shapes.append(shape)

    def AlignAndDistribute(self, method_h, method_v, align_to, dist_area, outline, text_origin, px, py, drect):
        self.align_and_distribute_calls.append({
            "method_h": method_h,
            "method_v": method_v,
            "align_to": align_to,
        })
        # Simulate left alignment to reference shape (first in range)
        if method_h == 2 and align_to == 0 and len(self.shapes) >= 2:
            ref_x = self.shapes[0].PositionX
            for s in self.shapes:
                s.PositionX = ref_x
        # Simulate horizontal centering to page center
        elif method_h == 3 and align_to == 2:
            page_w = self.doc.ActivePage.SizeWidth
            for s in self.shapes:
                s.PositionX = (page_w - s.SizeWidth) / 2.0

    def AlignRangeToPage(self, align_type: int) -> None:
        self.align_range_to_page_calls.append(align_type)

    def AlignRangeToPageCenter(self, align_type: int) -> None:
        self.align_range_to_page_center_calls.append(align_type)

    def Group(self) -> _MockShape:
        grp = _MockShape("AI_Group_001", 1.0, 1.0, 4.0, 3.0, shape_type=7)
        grp.child_shapes = list(self.shapes)
        # In page shapes, replace the grouped shapes with the group
        for s in self.shapes:
            if s in self.doc.ActivePage.shapes:
                self.doc.ActivePage.shapes.remove(s)
        self.doc.ActivePage.shapes.append(grp)
        return grp


class _MockLayer:
    def __init__(self, shapes: list[_MockShape]) -> None:
        self.shapes = shapes


class _MockPage:
    def __init__(self, width: float = 8.5, height: float = 11.0) -> None:
        self.SizeWidth = width
        self.SizeHeight = height
        self.shapes: list[_MockShape] = []
        self.ActiveLayer = _MockLayer(self.shapes)
        self.Shapes = _MockShapesCollection(self.shapes)


class _MockDocument:
    def __init__(self, width: float = 8.5, height: float = 11.0) -> None:
        self.Name = "TestAlignDoc"
        self.Unit = 1
        self.ReferencePoint = 5
        self.ActivePage = _MockPage(width, height)


class _MockApp:
    def __init__(self, doc: _MockDocument) -> None:
        self.ActiveDocument = doc
        self.doc = doc
        self.shape_ranges: list[_MockShapeRange] = []

    def CreateShapeRange(self) -> _MockShapeRange:
        sr = _MockShapeRange(self.doc)
        self.shape_ranges.append(sr)
        return sr


class AlignAndGroupUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = CorelBridge()
        self.doc = _MockDocument(8.5, 11.0)
        self.app = _MockApp(self.doc)
        self.bridge.app = self.app
        self.bridge.target_doc = self.doc
        self.bridge.target_doc_name = self.doc.Name

        # Populate document with shapes
        self.rect1 = _MockShape("Rect1", 1.0, 2.0, 2.0, 1.0)
        self.rect2 = _MockShape("Rect2", 4.0, 5.0, 3.0, 2.0)
        self.doc.ActivePage.shapes.extend([self.rect1, self.rect2])

    def test_align_objects_validation(self) -> None:
        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_objects(["Solo"])
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_objects(["Same", "Same"])
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_objects(["Rect1", "Rect2"], horizontal="invalid")
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_objects(["Rect1", "Rect2"], horizontal="none", vertical="none")
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_objects(["Rect1", "Rect2"], horizontal="left", align_to="invalid_target")
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_align_objects_success(self) -> None:
        res = self.bridge.align_objects(["Rect1", "Rect2"], horizontal="left", align_to="last_selected")
        self.assertTrue(res["aligned"])
        self.assertEqual(res["align_to"], "last_selected")
        self.assertEqual(res["horizontal"], "left")
        self.assertEqual(res["object_count"], 2)
        # Rect1 PositionX should equal Rect2 PositionX (4.0)
        self.assertEqual(self.rect1.PositionX, 4.0)

    def test_align_to_page_validation(self) -> None:
        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_to_page([])
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_to_page(["Rect1", "Rect1"])
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.align_to_page(["Rect1"], horizontal="none", vertical="none")
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_align_to_page_individual(self) -> None:
        res = self.bridge.align_to_page(["Rect1"], horizontal="center")
        self.assertTrue(res["aligned"])
        self.assertEqual(res["horizontal"], "center")
        self.assertFalse(res["align_as_group"])
        expected_x = (8.5 - 2.0) / 2.0
        self.assertAlmostEqual(self.rect1.PositionX, expected_x)

    def test_align_to_page_as_group(self) -> None:
        res = self.bridge.align_to_page(["Rect1", "Rect2"], horizontal="center", vertical="center", align_as_group=True)
        self.assertTrue(res["aligned"])
        self.assertTrue(res["align_as_group"])
        sr = self.app.shape_ranges[-1]
        self.assertEqual(len(sr.align_range_to_page_center_calls), 1)

    def test_group_shapes_validation(self) -> None:
        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.group_shapes(["OnlyOne"])
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.group_shapes(["Dup", "Dup"])
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_group_shapes_success(self) -> None:
        res = self.bridge.group_shapes(["Rect1", "Rect2"], group_name="MyCustomGroup")
        self.assertTrue(res["grouped"])
        self.assertEqual(res["group_name"], "MyCustomGroup")
        self.assertEqual(res["shape_count"], 2)
        self.assertIn("Rect1", res["child_names"])
        self.assertIn("Rect2", res["child_names"])
        # In page shapes, original 2 should be replaced by 1 group shape
        self.assertEqual(len(self.doc.ActivePage.shapes), 1)
        self.assertEqual(self.doc.ActivePage.shapes[0].Type, 7)

    def test_ungroup_shapes_validation(self) -> None:
        # Non-group shape cannot be ungrouped
        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.ungroup_shapes(object_name="Rect1")
        self.assertEqual(cm.exception.code, ErrorCode.INVALID_ARGUMENT)

        # Ambiguous selector
        with self.assertRaises(CorelBridgeError) as cm:
            self.bridge.ungroup_shapes(object_name="Rect1", shape_index=1)
        self.assertEqual(cm.exception.code, ErrorCode.AMBIGUOUS_SELECTOR)

    def test_ungroup_shapes_success(self) -> None:
        # First group them
        self.bridge.group_shapes(["Rect1", "Rect2"], group_name="GroupToUngroup")

        res = self.bridge.ungroup_shapes(object_name="GroupToUngroup", ungroup_all=False)
        self.assertTrue(res["ungrouped"])
        self.assertEqual(res["object_name"], "GroupToUngroup")
        self.assertEqual(res["shapes_released"], 2)


if __name__ == "__main__":
    unittest.main()
