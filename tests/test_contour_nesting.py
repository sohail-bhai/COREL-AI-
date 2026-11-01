from __future__ import annotations

import unittest

from corel_operator.corel_bridge import CorelBridge
from corel_operator.contour_nesting import (
    classify_imposition_job,
    contours_have_conflicts,
    plan_contour_nesting,
)
from corel_operator.errors import CorelBridgeError


INTERLOCKING_CARTON = [
    [0.0, 0.0],
    [4.0, 0.0],
    [4.0, 2.0],
    [1.0, 2.0],
    [1.0, 4.0],
    [0.0, 4.0],
]


class _Collection:
    def __init__(self, items=None, page=None, layer=None) -> None:
        self.items = list(items or [])
        self.page = page
        self.layer = layer

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _PageShapes:
    def __init__(self, page) -> None:
        self.page = page

    @property
    def items(self):
        return [shape for layer in self.page.Layers.items for shape in layer.Shapes.items]

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int):
        return self.items[index - 1]


class _Node:
    def __init__(self, point) -> None:
        self.PositionX = point[0]
        self.PositionY = point[1]


class _Polyline:
    def __init__(self, points) -> None:
        self.Nodes = _Collection([_Node(point) for point in points])


class _SubPath:
    Closed = True

    def __init__(self, points) -> None:
        self.points = points

    def GetPolyline(self, precision: int):
        return _Polyline(self.points)


class _Curve:
    def __init__(self, points) -> None:
        self.SubPaths = _Collection([_SubPath(points)])


class _Dieline:
    Type = 3
    StaticID = 20

    def __init__(self, points, name="CutContour") -> None:
        self.points = [list(point) for point in points]
        self.Name = name
        self.Layer = None
        self.Page = None

    @property
    def Curve(self):
        return _Curve(self.points)


class _Group:
    Type = 7
    StaticID = 10

    def __init__(self, owner, points, name="Repeat_Unit", add=True) -> None:
        self.owner = owner
        self.Name = name
        self.RotationAngle = 0.0
        self.Layer = owner.layer
        self.Page = owner.page
        self.dieline = _Dieline(points)
        self.dieline.Layer = self.Layer
        self.dieline.Page = self.Page
        self.Shapes = _Collection([self.dieline])
        if add:
            owner.items.append(self)

    @property
    def PositionX(self):
        return min(point[0] for point in self.dieline.points)

    @property
    def PositionY(self):
        return min(point[1] for point in self.dieline.points)

    @property
    def SizeWidth(self):
        return max(point[0] for point in self.dieline.points) - self.PositionX

    @property
    def SizeHeight(self):
        return max(point[1] for point in self.dieline.points) - self.PositionY

    def Duplicate(self, offset_x, offset_y):
        points = [[x + offset_x, y + offset_y] for x, y in self.dieline.points]
        duplicate = _Group(self.owner, points, self.Name)
        duplicate.RotationAngle = self.RotationAngle
        return duplicate

    def CopyToLayer(self, layer):
        return _Group(layer.Shapes, self.dieline.points, self.Name)

    def Rotate(self, degrees):
        left, bottom = self.PositionX, self.PositionY
        right, top = left + self.SizeWidth, bottom + self.SizeHeight
        self.dieline.points = [[left + right - x, bottom + top - y] for x, y in self.dieline.points]
        self.RotationAngle = (self.RotationAngle + degrees) % 360

    def SetPosition(self, x, y):
        if self.Page.document.fail_output_position and self.Page.Index > 1:
            raise RuntimeError("forced output placement failure")
        dx, dy = x - self.PositionX, y - self.PositionY
        self.dieline.points = [[px + dx, py + dy] for px, py in self.dieline.points]


class _Layer:
    def __init__(self, page, name) -> None:
        self.page = page
        self.Name = name
        self.Shapes = _Collection(page=page, layer=self)

    def Activate(self):
        self.page.ActiveLayer = self


class _Page:
    def __init__(self, document, index, width=8.0, height=6.0) -> None:
        self.document = document
        self.Index = index
        self.Name = f"Page {index}"
        self.Layers = _Collection()
        self.ActiveLayer = self.CreateLayer("Layer 1")
        self.Shapes = _PageShapes(self)
        self.SizeWidth = width
        self.SizeHeight = height

    def SetSize(self, width, height):
        self.SizeWidth = width
        self.SizeHeight = height

    def CreateLayer(self, name):
        layer = _Layer(self, name)
        self.Layers.items.append(layer)
        self.ActiveLayer = layer
        return layer

    def Activate(self):
        self.document._active_page = self

    def Delete(self):
        self.document.Pages.items.remove(self)
        for index, page in enumerate(self.document.Pages.items, start=1):
            page.Index = index
        self.document._active_page = self.document.Pages.items[0]


class _Document:
    Name = "Contour Test"
    FullFileName = ""

    def __init__(self) -> None:
        self.Unit = 1
        self.ReferencePoint = 5
        self.fail_output_position = False
        first_page = _Page(self, 1)
        self.Pages = _Collection([first_page])
        self._active_page = first_page
        _Group(first_page.ActiveLayer.Shapes, INTERLOCKING_CARTON)
        self.snapshot = None

    @property
    def ActivePage(self):
        return self._active_page

    def AddPagesEx(self, count, width, height):
        for _ in range(count):
            page = _Page(self, len(self.Pages.items) + 1, width, height)
            self.Pages.items.append(page)
            self._active_page = page

    def DeletePages(self, start_page, count=1):
        for _ in range(count):
            self.Pages.items[start_page - 1].Delete()

    def BeginCommandGroup(self, name):
        self.snapshot = True

    def EndCommandGroup(self):
        pass

    def Undo(self):
        pass


class ContourNestingTests(unittest.TestCase):
    def test_obvious_rectangle_does_not_ask_about_cutting(self) -> None:
        result = classify_imposition_job("rectangular")

        self.assertTrue(result["ready"])
        self.assertFalse(result["requires_clarification"])
        self.assertEqual(result["workflow"], "rectangular_n_up")
        self.assertEqual(result["questions"], [])

    def test_non_rectangular_job_asks_only_missing_production_questions(self) -> None:
        unknown = classify_imposition_job("contour", True)
        known = classify_imposition_job("contour", True, "digital_cutter", True)

        self.assertEqual([item["id"] for item in unknown["questions"]], ["cutting_method"])
        self.assertTrue(known["ready"])
        self.assertEqual(known["questions"], [])
        self.assertEqual(known["workflow"], "contour_nesting")

    def test_combined_source_is_rejected_as_a_repeat_unit(self) -> None:
        result = classify_imposition_job("contour", True, "die_cut", True, True)

        self.assertFalse(result["ready"])
        self.assertEqual(result["blocking_issues"][0]["code"], "COMBINED_SOURCE_NOT_REPEAT_UNIT")

    def test_alternating_180_rows_improve_capacity(self) -> None:
        result = plan_contour_nesting(
            INTERLOCKING_CARTON,
            8.0,
            6.0,
            quantity=4,
            margin_inches=0,
            cutting_method="digital_cutter",
            allow_180_rotation=True,
        )

        self.assertTrue(result["ready"])
        self.assertEqual(result["layout_strategy"], "alternating_0_180_rows")
        self.assertEqual(result["copies_per_sheet"], 4)
        self.assertTrue(result["nested_rows"])
        self.assertEqual([row["rotation_degrees"] for row in result["row_details"]], [0, 180])
        uniform = next(item for item in result["alternatives"] if item["layout_strategy"] == "upright_contour_rows")
        self.assertEqual(uniform["capacity"], 2)

    def test_bleed_and_gutter_are_collision_clearance(self) -> None:
        result = plan_contour_nesting(
            INTERLOCKING_CARTON,
            8.6,
            6.6,
            quantity=4,
            margin_inches=0,
            gutter_inches=0.1,
            bleed_inches=0.1,
            cutting_method="die_cut",
            allow_180_rotation=True,
        )

        self.assertEqual(result["required_contour_clearance_inches"], 0.3)
        self.assertEqual(result["effective_contour_clearance_inches"], 0.3005)
        self.assertEqual(result["copies_per_sheet"], 4)

    def test_guillotine_job_cannot_use_contour_interlocking(self) -> None:
        with self.assertRaises(CorelBridgeError):
            plan_contour_nesting(
                INTERLOCKING_CARTON,
                8,
                6,
                cutting_method="guillotine",
                allow_180_rotation=True,
            )

    def test_transformed_contour_verification_detects_overlap(self) -> None:
        shifted = [[x + 5.0, y] for x, y in INTERLOCKING_CARTON]

        self.assertTrue(contours_have_conflicts([INTERLOCKING_CARTON, INTERLOCKING_CARTON], 0))
        self.assertFalse(contours_have_conflicts([INTERLOCKING_CARTON, shifted], 0.1))

    def test_repeat_inspection_returns_conditional_questions(self) -> None:
        bridge = CorelBridge()
        bridge.target_doc = _Document()

        result = bridge.inspect_repeat_unit("Repeat_Unit", "CutContour")

        self.assertEqual(result["footprint_kind"], "contour")
        self.assertFalse(result["ready"])
        self.assertEqual([item["id"] for item in result["questions"]], ["cutting_method"])

    def test_repeat_inspection_does_not_question_an_obvious_rectangle(self) -> None:
        document = _Document()
        document.ActivePage.Shapes.items[0].dieline.points = [
            [0, 0], [4, 0], [4, 3], [0, 3],
        ]
        bridge = CorelBridge()
        bridge.target_doc = document

        result = bridge.inspect_repeat_unit("Repeat_Unit", "CutContour")

        self.assertEqual(result["footprint_kind"], "rectangular")
        self.assertTrue(result["ready"])
        self.assertEqual(result["workflow"], "rectangular_n_up")
        self.assertEqual(result["questions"], [])

    def test_execution_keeps_every_repeat_as_an_independent_group(self) -> None:
        bridge = CorelBridge()
        document = _Document()
        bridge.target_doc = document
        source = document.ActivePage.Shapes.items[0]
        source_points = [list(point) for point in source.dieline.points]
        _Group(
            document.ActivePage.ActiveLayer.Shapes,
            [[5.0, 0.0], [6.0, 0.0], [6.0, 1.0], [5.0, 1.0]],
            "Unrelated_Source_Page_Object",
        )

        result = bridge.prepare_contour_nesting(
            "Repeat_Unit",
            "CutContour",
            8,
            6,
            copies=4,
            margin_inches=0,
            cutting_method="digital_cutter",
            allow_180_rotation=True,
        )

        self.assertTrue(result["prepared"])
        self.assertTrue(result["independent_repeat_groups"])
        self.assertTrue(result["source_preserved"])
        self.assertEqual(result["created_count"], 4)
        self.assertEqual([item["rotation_degrees"] for item in result["objects"]], [0, 0, 180, 180])
        self.assertEqual(document.Pages.Count, 2)
        self.assertEqual(document.Pages.Item(1).Shapes.Count, 2)
        self.assertEqual(document.Pages.Item(1).Shapes.Item(1).Name, "Repeat_Unit")
        self.assertEqual(document.Pages.Item(1).Shapes.Item(1).dieline.points, source_points)
        self.assertEqual(document.Pages.Item(1).Shapes.Item(2).Name, "Unrelated_Source_Page_Object")
        self.assertEqual(
            [shape.Name for shape in bridge.target_doc.ActivePage.Shapes.items],
            ["Nested_Copy_001", "Nested_Copy_002", "Nested_Copy_003", "Nested_Copy_004"],
        )

    def test_orchestrator_plans_then_executes_only_matching_fingerprint(self) -> None:
        bridge = CorelBridge()
        document = _Document()
        bridge.target_doc = document

        planned = bridge.prepare_imposition_job(
            "Repeat_Unit",
            "CutContour",
            8,
            6,
            quantity=4,
            margin_inches=0,
            cutting_method="digital_cutter",
            allow_180_rotation=True,
        )

        self.assertEqual(planned["status"], "planned")
        self.assertTrue(planned["ready_for_execution"])
        self.assertTrue(planned["plan_fingerprint"].startswith("sha256:"))
        self.assertEqual(document.Pages.Count, 1)

        completed = bridge.prepare_imposition_job(
            "Repeat_Unit",
            "CutContour",
            8,
            6,
            quantity=4,
            margin_inches=0,
            cutting_method="digital_cutter",
            allow_180_rotation=True,
            confirm_execution=True,
            approved_plan_fingerprint=planned["plan_fingerprint"],
        )

        self.assertEqual(completed["status"], "completed")
        self.assertTrue(completed["source_preserved"])
        self.assertEqual(completed["execution"]["output"]["page_index"], 2)
        self.assertEqual(document.Pages.Item(1).Shapes.Item(1).Name, "Repeat_Unit")

    def test_orchestrator_rejects_changed_source_after_approval(self) -> None:
        bridge = CorelBridge()
        document = _Document()
        bridge.target_doc = document
        planned = bridge.prepare_imposition_job(
            "Repeat_Unit", "CutContour", 8, 6, quantity=4, margin_inches=0,
            cutting_method="digital_cutter", allow_180_rotation=True,
        )
        document.ActivePage.Shapes.Item(1).SetPosition(0.25, 0.0)

        with self.assertRaises(CorelBridgeError) as raised:
            bridge.prepare_imposition_job(
                "Repeat_Unit", "CutContour", 8, 6, quantity=4, margin_inches=0,
                cutting_method="digital_cutter", allow_180_rotation=True,
                confirm_execution=True,
                approved_plan_fingerprint=planned["plan_fingerprint"],
            )

        self.assertEqual(raised.exception.code.value, "CONFIRMATION_REQUIRED")
        self.assertEqual(document.Pages.Count, 1)

    def test_orchestrator_asks_rotation_only_when_capacity_improves(self) -> None:
        bridge = CorelBridge()
        bridge.target_doc = _Document()

        result = bridge.prepare_imposition_job(
            "Repeat_Unit", "CutContour", 8, 6, quantity=4, margin_inches=0,
            cutting_method="digital_cutter",
        )

        self.assertEqual(result["status"], "needs_input")
        self.assertEqual([item["id"] for item in result["questions"]], ["allow_180_rotation"])
        self.assertEqual(result["questions"][0]["impact"]["upright_copies_per_sheet"], 2)
        self.assertEqual(result["questions"][0]["impact"]["rotated_copies_per_sheet"], 4)

    def test_orchestrator_skips_rotation_question_when_capacity_is_unchanged(self) -> None:
        bridge = CorelBridge()
        bridge.target_doc = _Document()

        result = bridge.prepare_imposition_job(
            "Repeat_Unit", "CutContour", 4, 4, quantity=1, margin_inches=0,
            cutting_method="digital_cutter",
        )

        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["questions"], [])
        self.assertTrue(result["ready_for_execution"])
        self.assertIn("does not improve sheet capacity", result["warnings"][0])

    def test_orchestrator_routes_rectangle_without_cutter_question(self) -> None:
        document = _Document()
        document.ActivePage.Shapes.items[0].dieline.points = [
            [0, 0], [4, 0], [4, 3], [0, 3],
        ]
        bridge = CorelBridge()
        bridge.target_doc = document

        result = bridge.prepare_imposition_job(
            "Repeat_Unit", "CutContour", 8, 6, quantity=2, margin_inches=0,
        )

        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["workflow"], "rectangular_n_up")
        self.assertEqual(result["questions"], [])
        self.assertTrue(result["ready_for_execution"])

        completed = bridge.prepare_imposition_job(
            "Repeat_Unit", "CutContour", 8, 6, quantity=2, margin_inches=0,
            confirm_execution=True,
            approved_plan_fingerprint=result["plan_fingerprint"],
        )

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["execution"]["created_count"], 2)
        self.assertTrue(completed["source_preserved"])

    def test_failed_execution_removes_only_new_output_page(self) -> None:
        bridge = CorelBridge()
        document = _Document()
        document.fail_output_position = True
        bridge.target_doc = document
        source = document.ActivePage.Shapes.Item(1)
        original_points = [list(point) for point in source.dieline.points]

        with self.assertRaises(CorelBridgeError) as raised:
            bridge.prepare_contour_nesting(
                "Repeat_Unit", "CutContour", 8, 6, copies=4, margin_inches=0,
                cutting_method="digital_cutter", allow_180_rotation=True,
            )

        self.assertTrue(raised.exception.details["rollback_verified"])
        self.assertEqual(document.Pages.Count, 1)
        self.assertEqual(document.ActivePage.Shapes.Count, 1)
        self.assertEqual(document.ActivePage.Shapes.Item(1).Name, "Repeat_Unit")
        self.assertEqual(document.ActivePage.Shapes.Item(1).dieline.points, original_points)


if __name__ == "__main__":
    unittest.main()
