from __future__ import annotations

import unittest

from corel_operator.adapters import CorelX7Adapter
from corel_operator.diagnostics import collect_static_diagnostics, run_diagnostics
from corel_operator.version import BRIDGE_VERSION, TOOL_SCHEMA_VERSION


class StaticDiagnosticsTests(unittest.TestCase):
    def test_static_diagnostics_do_not_attempt_connection(self) -> None:
        report = collect_static_diagnostics()

        self.assertFalse(report["connection_attempted"])
        self.assertEqual(report["bridge_version"], BRIDGE_VERSION)
        self.assertEqual(report["tool_schema_version"], TOOL_SCHEMA_VERSION)
        self.assertEqual(report["profile"]["profile_id"], "coreldraw-x7-17")
        self.assertIn(CorelX7Adapter.EXPLICIT_PROG_ID, report["com_registrations"])
        self.assertIn(CorelX7Adapter.GENERIC_PROG_ID, report["com_registrations"])
        self.assertNotIn("coreldraw", report)

    def test_static_run_mode_remains_connection_free(self) -> None:
        report = run_diagnostics(connect=False)
        self.assertFalse(report["connection_attempted"])
        self.assertNotIn("com_connection", report)


if __name__ == "__main__":
    unittest.main()
