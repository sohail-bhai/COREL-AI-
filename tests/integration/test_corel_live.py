from __future__ import annotations

import os
import unittest

from corel_operator.corel_bridge import CorelBridge


LIVE_ENABLED = os.environ.get("COREL_LIVE_TESTS") == "1"


@unittest.skipUnless(
    LIVE_ENABLED,
    "Set COREL_LIVE_TESTS=1 explicitly to run read-only tests against CorelDRAW X7.",
)
class CorelReadOnlyLiveTests(unittest.TestCase):
    def test_status_reports_x7_without_binding_a_target(self) -> None:
        bridge = CorelBridge()
        status = bridge.connect()

        self.assertTrue(status["connected"])
        self.assertEqual(status["version_major"], 17)
        self.assertFalse(status["target_document_bound"])


if __name__ == "__main__":
    unittest.main()
