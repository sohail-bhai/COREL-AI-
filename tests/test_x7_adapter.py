from __future__ import annotations

import unittest

from corel_operator.adapters import CorelX7Adapter
from corel_operator.errors import CorelBridgeError, ErrorCode


class _X7Application:
    Version = "Version 17.0.0.491"
    VersionMajor = 17
    VersionMinor = 0
    VersionBuild = 491


class _X8Application:
    Version = "Version 18.0.0.448"
    VersionMajor = 18
    VersionMinor = 0
    VersionBuild = 448


class _StringOnlyX7Application:
    Version = "Version 17.0.0.491"


class X7AdapterTests(unittest.TestCase):
    def test_explicit_x7_prog_id_is_first_candidate(self) -> None:
        self.assertEqual(CorelX7Adapter.EXPLICIT_PROG_ID, "CorelDRAW.Application.17")
        self.assertEqual(
            CorelX7Adapter.CONNECTION_CANDIDATES[0],
            ("GetActiveObject", "CorelDRAW.Application.17"),
        )

    def test_verified_constants_match_installed_type_library_inventory(self) -> None:
        self.assertEqual(CorelX7Adapter.CDR_INCH, 1)
        self.assertEqual(CorelX7Adapter.CDR_BOTTOM_LEFT, 5)
        self.assertEqual(CorelX7Adapter.CDR_FILTER_CDR, 1795)
        self.assertEqual(CorelX7Adapter.CDR_CURRENT_VERSION, 0)
        self.assertEqual(CorelX7Adapter.CDR_ALL_PAGES, 0)
        self.assertEqual(CorelX7Adapter.CDR_TRUE, -1)
        self.assertEqual(CorelX7Adapter.CDR_FALSE, 0)
        self.assertEqual(CorelX7Adapter.CDR_TEXT_SHAPE, 6)
        self.assertEqual(CorelX7Adapter.CDR_GROUP_SHAPE, 7)

    def test_application_version_is_validated(self) -> None:
        info = CorelX7Adapter.validate_application(
            _X7Application(),
            CorelX7Adapter.EXPLICIT_PROG_ID,
        )
        self.assertEqual(info["version_major"], 17)
        self.assertEqual(info["version_build"], 491)

    def test_version_string_fallback_detects_x7(self) -> None:
        info = CorelX7Adapter.validate_application(_StringOnlyX7Application())
        self.assertEqual(info["version_major"], 17)
        self.assertEqual(info["version_minor"], 0)

    def test_unexpected_major_version_is_rejected(self) -> None:
        with self.assertRaises(CorelBridgeError) as context:
            CorelX7Adapter.validate_application(
                _X8Application(),
                CorelX7Adapter.GENERIC_PROG_ID,
            )
        self.assertEqual(context.exception.code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(context.exception.details["expected_major"], 17)
        self.assertEqual(context.exception.details["detected_major"], 18)

    def test_capability_support_is_truthful(self) -> None:
        self.assertTrue(CorelX7Adapter.supports("shape.create_rectangle"))
        self.assertTrue(CorelX7Adapter.supports("object.inspect"))
        self.assertTrue(CorelX7Adapter.supports("object.find"))
        self.assertFalse(CorelX7Adapter.supports("object.find", require_verified=True))
        for capability in ("object.bounds", "text.inspect", "fill.inspect"):
            self.assertTrue(CorelX7Adapter.supports(capability))
            self.assertFalse(CorelX7Adapter.supports(capability, require_verified=True))
        self.assertFalse(CorelX7Adapter.supports("shape.create_rectangle", require_verified=True))
        self.assertFalse(CorelX7Adapter.supports("outline.width_points"))
        self.assertFalse(CorelX7Adapter.supports("unknown.capability"))
        details = CorelX7Adapter.capability_details("outline.width_points")
        self.assertEqual(details["status"], "research_required")

    def test_profile_summary_does_not_claim_verified_capabilities(self) -> None:
        summary = CorelX7Adapter.profile_summary()
        self.assertEqual(summary["profile_id"], "coreldraw-x7-17")
        self.assertEqual(summary["product_major"], 17)
        self.assertEqual(summary["preferred_prog_id"], "CorelDRAW.Application.17")
        self.assertEqual(summary["capability_count"], 40)
        self.assertEqual(summary["verified_capability_count"], 0)


if __name__ == "__main__":
    unittest.main()
