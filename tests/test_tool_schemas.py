from __future__ import annotations

import unittest

from scripts.validate_catalog import validate


class ToolSchemaTests(unittest.TestCase):
    def test_catalog_and_tool_schemas_are_consistent(self) -> None:
        counts = validate()

        self.assertEqual(counts["registered_tools"], 71)
        self.assertEqual(counts["registry_records"], 73)
        self.assertEqual(counts["matrix_rows"], 73)
        self.assertEqual(counts["examples_checked"], 219)
        self.assertEqual(counts["adapter_capabilities"], 56)
        self.assertGreaterEqual(counts["inventory_members"], 110)
        self.assertEqual(counts["enum_groups"], 21)


if __name__ == "__main__":
    unittest.main()
