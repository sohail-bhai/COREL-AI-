from __future__ import annotations

import unittest

from scripts.validate_catalog import validate


class ToolSchemaTests(unittest.TestCase):
    def test_catalog_and_tool_schemas_are_consistent(self) -> None:
        counts = validate()

        self.assertEqual(counts["registered_tools"], 29)
        self.assertEqual(counts["registry_records"], 34)
        self.assertEqual(counts["matrix_rows"], 34)
        self.assertEqual(counts["examples_checked"], 102)
        self.assertEqual(counts["adapter_capabilities"], 24)
        self.assertGreaterEqual(counts["inventory_members"], 103)
        self.assertEqual(counts["enum_groups"], 12)


if __name__ == "__main__":
    unittest.main()
