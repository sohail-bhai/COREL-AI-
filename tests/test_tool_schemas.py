from __future__ import annotations

import unittest

from scripts.validate_catalog import validate


class ToolSchemaTests(unittest.TestCase):
    def test_catalog_and_tool_schemas_are_consistent(self) -> None:
        counts = validate()

        self.assertEqual(counts["registered_tools"], 17)
        self.assertEqual(counts["registry_records"], 30)
        self.assertEqual(counts["matrix_rows"], 30)
        self.assertEqual(counts["examples_checked"], 90)
        self.assertEqual(counts["adapter_capabilities"], 18)
        self.assertGreaterEqual(counts["inventory_members"], 88)


if __name__ == "__main__":
    unittest.main()
