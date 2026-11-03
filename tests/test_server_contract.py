from __future__ import annotations

import unittest

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode


class _FakeDispatcher:
    def __init__(self, value=None, error: BaseException | None = None) -> None:
        self.value = value
        self.error = error
        self.calls: list[tuple[str, tuple, dict]] = []

    def call(self, method_name, *args, **kwargs):
        self.calls.append((method_name, args, kwargs))
        if self.error is not None:
            raise self.error
        return self.value


class ServerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_dispatcher = server.dispatcher

    def tearDown(self) -> None:
        server.dispatcher = self.original_dispatcher

    def test_corel_status_wrapper_returns_success_envelope(self) -> None:
        fake = _FakeDispatcher(
            {
                "connected": True,
                "active_document_open": False,
                "target_document_bound": False,
            }
        )
        server.dispatcher = fake

        result = server.corel_status()

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "corel_status")
        self.assertEqual(result["data"]["connected"], True)
        self.assertEqual(fake.calls, [("status", (), {})])

    def test_wrapper_returns_stable_error_envelope(self) -> None:
        fake = _FakeDispatcher(
            error=CorelBridgeError(
                "No target document is bound.",
                ErrorCode.NO_TARGET_DOCUMENT,
            )
        )
        server.dispatcher = fake

        result = server.list_objects()

        self.assertFalse(result["ok"])
        self.assertEqual(result["tool"], "list_objects")
        self.assertEqual(result["error"]["code"], "NO_TARGET_DOCUMENT")
        self.assertEqual(fake.calls, [("list_objects", (200,), {})])

    def test_inspection_wrappers_dispatch_expected_methods_and_arguments(self) -> None:
        fake = _FakeDispatcher({})
        server.dispatcher = fake

        server.list_open_documents()
        server.get_document_info()
        server.list_pages()
        server.get_page_bounds(2)
        server.list_layers(3)
        server.get_object_info("headline", 0)
        server.get_object_bounds("headline", 0)
        server.get_text_properties("headline", 0, 100)
        server.get_fill("headline", 0)

        self.assertEqual(
            fake.calls,
            [
                ("list_open_documents", (), {}),
                ("get_document_info", (), {}),
                ("list_pages", (), {}),
                ("get_page_bounds", (2,), {}),
                ("list_layers", (3,), {}),
                ("get_object_info", ("headline", 0), {}),
                ("get_object_bounds", ("headline", 0), {}),
                ("get_text_properties", ("headline", 0, 100), {}),
                ("get_fill", ("headline", 0), {}),
            ],
        )

    def test_workflow_wrappers_return_standard_result_envelopes(self) -> None:
        layout_result = server.calculate_sheet_layout(3.0, 2.0, 10.0, 8.0)
        self.assertTrue(layout_result["ok"])
        self.assertEqual(layout_result["tool"], "calculate_sheet_layout")
        self.assertIn("capacity", layout_result["data"])

        best_fit = server.calculate_sheet_layout(
            5.0, 2.0, 9.0, 14.0,
            rotation_policy="best_fit",
            requested_quantity=100,
        )
        self.assertTrue(best_fit["ok"])
        self.assertEqual(best_fit["data"]["capacity"], 11)
        self.assertEqual(best_fit["data"]["sheets_required"], 10)

        routing = server.classify_imposition_job("rectangular")
        self.assertTrue(routing["ok"])
        self.assertEqual(routing["data"]["workflow"], "rectangular_n_up")
        self.assertEqual(routing["data"]["questions"], [])

        contour = server.plan_contour_nesting(
            [[0, 0], [4, 0], [4, 2], [1, 2], [1, 4], [0, 4]],
            8,
            6,
            quantity=4,
            margin_inches=0,
            cutting_method="digital_cutter",
            allow_180_rotation=True,
        )
        self.assertTrue(contour["ok"])
        self.assertEqual(contour["data"]["copies_per_sheet"], 4)

        bad_layout = server.calculate_sheet_layout(-1.0, 2.0, 10.0, 8.0)
        self.assertFalse(bad_layout["ok"])
        self.assertEqual(bad_layout["error"]["code"], "INVALID_ARGUMENT")

        batch_result = server.plan_chest_number_batch(1, 10, zero_pad_width=3)
        self.assertTrue(batch_result["ok"])
        self.assertEqual(batch_result["tool"], "plan_chest_number_batch")
        self.assertEqual(batch_result["data"]["count"], 10)

        bad_batch = server.plan_chest_number_batch(10, 1)
        self.assertFalse(bad_batch["ok"])
        self.assertEqual(bad_batch["error"]["code"], "INVALID_ARGUMENT")

    def test_find_objects_dispatches_every_filter_and_limit(self) -> None:
        fake = _FakeDispatcher({"document_name": "Target.cdr", "matches": []})
        server.dispatcher = fake

        result = server.find_objects("title", 6, "Member", 2, "Artwork", 5, False, True, 3, 25)

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "find_objects")
        self.assertEqual(result["target_document"], {"name": "Target.cdr"})
        self.assertEqual(fake.calls, [
            ("find_objects", ("title", 6, "Member", 2, "Artwork", 5, False, True, 3, 25), {})
        ])

    def test_find_objects_preserves_incomplete_results_and_stable_errors(self) -> None:
        fake = _FakeDispatcher({
            "matches": [], "truncated": True, "incomplete_reasons": ["max_scan"],
        })
        server.dispatcher = fake
        result = server.find_objects(max_scan=1)
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["truncated"])
        self.assertEqual(result["data"]["incomplete_reasons"], ["max_scan"])

        fake.error = CorelBridgeError("No target is bound.", ErrorCode.NO_TARGET_DOCUMENT)
        result = server.find_objects()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "NO_TARGET_DOCUMENT")
        self.assertIsNone(result["data"])

    def test_create_chest_number_batch_dispatches(self) -> None:
        fake = _FakeDispatcher({"created": True, "created_count": 2})
        server.dispatcher = fake

        result = server.create_chest_number_batch(1, 2, 4.0, 3.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "create_chest_number_batch")
        self.assertEqual(fake.calls[0][0], "create_chest_number_batch")

    def test_imposition_orchestrator_dispatches_approval_fields(self) -> None:
        fake = _FakeDispatcher({"status": "planned", "plan_fingerprint": "sha256:abc"})
        server.dispatcher = fake

        result = server.prepare_imposition_job(
            "Repeat_Unit",
            "CutContour",
            8.0,
            6.0,
            quantity=4,
            cutting_method="digital_cutter",
            allow_180_rotation=True,
            confirm_execution=True,
            approved_plan_fingerprint="sha256:abc",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "prepare_imposition_job")
        self.assertEqual(fake.calls[0][0], "prepare_imposition_job")
        self.assertEqual(fake.calls[0][1][-2:], (True, "sha256:abc"))

    def test_design_plan_wrappers_contract(self) -> None:
        plan = {
            "version": "1.0",
            "name": "contract_test_plan",
            "canvas": {"width_inches": 8.5, "height_inches": 11.0},
            "elements": [{"id": "box_01", "type": "rectangle", "x_inches": 1.0, "y_inches": 1.0, "width_inches": 2.0, "height_inches": 1.0}],
        }
        val_res = server.validate_design_plan(plan)
        self.assertTrue(val_res["ok"])
        self.assertEqual(val_res["tool"], "validate_design_plan")
        self.assertTrue(val_res["data"]["valid"])

        prev_res = server.preview_design_plan(plan)
        self.assertTrue(prev_res["ok"])
        self.assertEqual(prev_res["tool"], "preview_design_plan")
        self.assertIn("bounding_box", prev_res["data"])

        fake = _FakeDispatcher({"executed": True, "elements_executed": 1})
        server.dispatcher = fake

        exec_res = server.execute_design_plan(plan)
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["tool"], "execute_design_plan")
        self.assertEqual(fake.calls[0][0], "execute_design_plan")

    def test_align_and_group_wrappers_contract(self) -> None:
        fake = _FakeDispatcher({"aligned": True, "object_count": 2})
        server.dispatcher = fake

        res_align = server.align_objects(["Box1", "Box2"], horizontal="left")
        self.assertTrue(res_align["ok"])
        self.assertEqual(res_align["tool"], "align_objects")
        self.assertEqual(fake.calls[0][0], "align_objects")

        fake_page = _FakeDispatcher({"aligned": True, "align_to": "page"})
        server.dispatcher = fake_page
        res_page = server.align_to_page(["Box1"], horizontal="center", vertical="center")
        self.assertTrue(res_page["ok"])
        self.assertEqual(res_page["tool"], "align_to_page")
        self.assertEqual(fake_page.calls[0][0], "align_to_page")

        fake_group = _FakeDispatcher({"grouped": True, "group_name": "TestGrp"})
        server.dispatcher = fake_group
        res_group = server.group_shapes(["Box1", "Box2"], "TestGrp")
        self.assertTrue(res_group["ok"])
        self.assertEqual(res_group["tool"], "group_shapes")
        self.assertEqual(fake_group.calls[0][0], "group_shapes")

        fake_ungroup = _FakeDispatcher({"ungrouped": True, "object_name": "TestGrp"})
        server.dispatcher = fake_ungroup
        res_ungroup = server.ungroup_shapes(object_name="TestGrp")
        self.assertTrue(res_ungroup["ok"])
        self.assertEqual(res_ungroup["tool"], "ungroup_shapes")
        self.assertEqual(fake_ungroup.calls[0][0], "ungroup_shapes")


if __name__ == "__main__":
    unittest.main()
