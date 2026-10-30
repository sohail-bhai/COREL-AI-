from __future__ import annotations

import json
import unittest

from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import error_result, success_result
from corel_operator.version import (
    BRIDGE_VERSION,
    CAPABILITY_PROFILE_ID,
    TOOL_SCHEMA_VERSION,
)


class ResultContractTests(unittest.TestCase):
    def test_success_envelope_preserves_data_and_metadata(self) -> None:
        result = success_result(
            "create_document",
            {"created": True, "target_document_name": "Graphic1"},
            12.34567,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "create_document")
        self.assertEqual(result["bridge_version"], BRIDGE_VERSION)
        self.assertEqual(result["tool_schema_version"], TOOL_SCHEMA_VERSION)
        self.assertEqual(result["profile_id"], CAPABILITY_PROFILE_ID)
        self.assertEqual(result["target_document"], {"name": "Graphic1"})
        self.assertEqual(result["data"]["created"], True)
        self.assertEqual(result["warnings"], [])
        self.assertIsNone(result["error"])
        self.assertEqual(result["duration_ms"], 12.346)
        json.dumps(result)

    def test_success_envelope_promotes_legacy_warning(self) -> None:
        result = success_result(
            "export_pdf",
            {"exported": True, "warning": "Check PDF settings."},
            -1,
        )

        self.assertEqual(result["warnings"], ["Check PDF settings."])
        self.assertEqual(result["duration_ms"], 0.0)

    def test_expected_bridge_error_keeps_stable_code_and_safe_details(self) -> None:
        exc = CorelBridgeError(
            "No target is bound.",
            ErrorCode.NO_TARGET_DOCUMENT,
            {"next_step": "create_document"},
        )
        result = error_result("list_objects", exc, 1.25)

        self.assertFalse(result["ok"])
        self.assertIsNone(result["data"])
        self.assertEqual(result["error"]["code"], "NO_TARGET_DOCUMENT")
        self.assertEqual(result["error"]["message"], "No target is bound.")
        self.assertEqual(result["error"]["details"], {"next_step": "create_document"})
        self.assertEqual(result["duration_ms"], 1.25)
        json.dumps(result)

    def test_timeout_has_stable_error(self) -> None:
        result = error_result("save_document", TimeoutError(), 120000)

        self.assertEqual(result["error"]["code"], "OPERATION_TIMEOUT")
        self.assertIn("120-second", result["error"]["message"])

    def test_unexpected_error_does_not_expose_exception_message(self) -> None:
        result = error_result("corel_status", ValueError("private path or content"), 0)

        self.assertEqual(result["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("private path", result["error"]["message"])
        self.assertEqual(result["error"]["details"], {"exception_type": "ValueError"})

    def test_worker_runtime_error_is_classified(self) -> None:
        result = error_result(
            "corel_status",
            RuntimeError("CorelDRAW COM worker is not running."),
            0,
        )

        self.assertEqual(result["error"]["code"], "WORKER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
