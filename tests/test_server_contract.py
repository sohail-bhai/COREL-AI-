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


if __name__ == "__main__":
    unittest.main()
