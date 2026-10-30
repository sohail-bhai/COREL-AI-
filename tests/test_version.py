from __future__ import annotations

import re
import unittest

import corel_operator
from corel_operator.version import (
    BRIDGE_VERSION,
    CAPABILITY_PROFILE_ID,
    SUPPORTED_CAPABILITY_PROFILES,
    TOOL_SCHEMA_VERSION,
)


class VersionContractTests(unittest.TestCase):
    def test_bridge_version_is_authoritative_semver(self) -> None:
        self.assertEqual(corel_operator.__version__, BRIDGE_VERSION)
        self.assertRegex(BRIDGE_VERSION, re.compile(r"^0\.[0-9]+\.[0-9]+$"))

    def test_tool_schema_version_is_positive_integer(self) -> None:
        self.assertIsInstance(TOOL_SCHEMA_VERSION, int)
        self.assertGreaterEqual(TOOL_SCHEMA_VERSION, 1)

    def test_x7_profile_is_supported(self) -> None:
        self.assertEqual(CAPABILITY_PROFILE_ID, "coreldraw-x7-17")
        self.assertIn(CAPABILITY_PROFILE_ID, SUPPORTED_CAPABILITY_PROFILES)


if __name__ == "__main__":
    unittest.main()
