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

        self.assertEqual(
            fake.calls,
            [
                ("list_open_documents", (), {}),
                ("get_document_info", (), {}),
                ("list_pages", (), {}),
                ("get_page_bounds", (2,), {}),
                ("list_layers", (3,), {}),
                ("get_object_info", ("headline", 0), {}),
            ],
        )

    def test_workflow_wrappers_return_standard_result_envelopes(self) -> None:
        layout_result = server.calculate_sheet_layout(3.0, 2.0, 10.0, 8.0)
        self.assertTrue(layout_result["ok"])
        self.assertEqual(layout_result["tool"], "calculate_sheet_layout")
        self.assertIn("capacity", layout_result["data"])

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


if __name__ == "__main__":
    unittest.main()
