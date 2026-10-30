from __future__ import annotations

import unittest

from corel_operator.corel_bridge import CorelBridge
from corel_operator.version import (
    BRIDGE_VERSION,
    CAPABILITY_PROFILE_ID,
    TOOL_SCHEMA_VERSION,
)


class _FakeApplication:
    Version = "Version 17.0.0.491"
    VersionMajor = 17
    VersionMinor = 0
    VersionBuild = 491
    Visible = True
    ActiveDocument = None


class StatusMetadataTests(unittest.TestCase):
    def test_status_reports_version_profile_runtime_and_connection_metadata(self) -> None:
        bridge = CorelBridge()
        bridge.app = _FakeApplication()
        bridge.prog_id_used = "CorelDRAW.Application"
        bridge.connection_mode = "GetActiveObject"

        status = bridge.status()

        self.assertTrue(status["connected"])
        self.assertEqual(status["bridge_version"], BRIDGE_VERSION)
        self.assertEqual(status["tool_schema_version"], TOOL_SCHEMA_VERSION)
        self.assertEqual(status["capability_profile_id"], CAPABILITY_PROFILE_ID)
        self.assertEqual(status["prog_id_used"], "CorelDRAW.Application")
        self.assertEqual(status["connection_mode"], "GetActiveObject")
        self.assertEqual(status["version_major"], 17)
        self.assertEqual(status["version_minor"], 0)
        self.assertEqual(status["version_build"], 491)
        self.assertFalse(status["active_document_open"])
        self.assertFalse(status["target_document_bound"])
        self.assertGreater(status["runtime"]["python_bitness"], 0)
        self.assertIsInstance(status["runtime"]["python_version"], str)


if __name__ == "__main__":
    unittest.main()
