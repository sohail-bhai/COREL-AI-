from __future__ import annotations

import unittest

from scripts.validate_catalog import validate


class ToolSchemaTests(unittest.TestCase):
    def test_catalog_and_tool_schemas_are_consistent(self) -> None:
        counts = validate()

        self.assertEqual(counts["registered_tools"], 84)
        self.assertEqual(counts["registry_records"], 86)
        self.assertEqual(counts["matrix_rows"], 86)
        self.assertEqual(counts["examples_checked"], 258)
        self.assertEqual(counts["adapter_capabilities"], 65)
        self.assertGreaterEqual(counts["inventory_members"], 110)
        self.assertEqual(counts["enum_groups"], 28)


if __name__ == "__main__":
    unittest.main()
