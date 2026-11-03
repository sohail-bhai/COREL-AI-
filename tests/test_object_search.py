from __future__ import annotations

import json
import unittest

from fake_documents import attach_open_document
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator

from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result


class _Collection:
    def __init__(self, *items):
        self.items = list(items)
        self.reads = 0

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        self.reads += 1
        return self.items[index - 1]


def _shape(name, static_id, type_code=1, text=None, children=()):
    shape = SimpleNamespace(Name=name, StaticID=static_id, Type=type_code)
    if type_code == 6:
        shape.Text = SimpleNamespace(Story=SimpleNamespace(Text=text or ""))
    if type_code == 7:
        shape.Shapes = _Collection(*children)
    return shape


def _layer(name, *shapes):
    return SimpleNamespace(Name=name, Shapes=_Collection(*shapes))


def _page(*layers):
    collection = _Collection(*layers)
    return SimpleNamespace(AllLayers=collection, Layers=collection)


class ObjectSearchTests(unittest.TestCase):
    def setUp(self):
        self.first = _shape("TITLE", 101, 6, "Member Alice")
        self.child = _shape("TITLE", 103, 6, "Member Bob")
        self.deep = _shape("Deep", 105, 6, "Straße")
        inner = _shape("Inner", 104, 7, children=(self.deep,))
        group = _shape("Group", 102, 7, children=(self.child, inner))
        self.front = _page(_layer("Artwork", self.first, group), _layer("Guides"))
        self.back = _page(_layer("Artwork", _shape("TITLE", 201, 6, "Member Carol")))
        self.document = SimpleNamespace(
            Name="Target.cdr", Pages=_Collection(self.front, self.back),
            ActivePage=self.back, Unit=1, ReferencePoint=5, Dirty=False,
        )
        self.other = SimpleNamespace(Name="Other.cdr")
        self.bridge = CorelBridge()
        self.bridge.app = SimpleNamespace(ActiveDocument=self.other)
        attach_open_document(self.bridge, self.document)

    def test_all_pages_nested_duplicates_are_distinct_and_deterministic(self):
        first = self.bridge.find_objects(name_contains="title")
        second = self.bridge.find_objects(name_contains="title")

        self.assertEqual(first, second)
        self.assertEqual([m["static_id"] for m in first["matches"]], [101, 103, 201])
        self.assertEqual([m["shape_path"] for m in first["matches"]], [[1], [2, 1], [1]])
        self.assertEqual([m["group_depth"] for m in first["matches"]], [0, 1, 0])
        self.assertEqual([m["page_index"] for m in first["matches"]], [1, 1, 2])
        self.assertEqual(first["scanned_objects"], 6)
        self.assertEqual(first["scanned_entries"], 11)
        self.assertFalse(first["truncated"])
        self.assertEqual(first["matches"][1]["object_id"], "doc-0001:shape:103")

    def test_inspection_does_not_activate_select_edit_or_connect(self):
        before = vars(self.document).copy()
        layers_before = vars(self.front).copy()
        shape_before = vars(self.first).copy()
        with patch.object(self.bridge, "connect", side_effect=AssertionError("must not connect")):
            self.bridge.find_objects(page_index=1)

        self.assertEqual(vars(self.document), before)
        self.assertEqual(vars(self.front), layers_before)
        self.assertEqual(vars(self.first), shape_before)
        self.assertIs(self.bridge.app.ActiveDocument, self.other)
        self.assertIs(self.bridge.target_doc, self.document)

    def test_page_layer_name_type_and_text_filters_combine_with_and(self):
        result = self.bridge.find_objects(
            name_contains="title", shape_type_code=6, text_contains="bob",
            page_index=1, layer_name="artwork",
        )
        self.assertEqual([m["static_id"] for m in result["matches"]], [103])
        self.assertEqual(result["matches"][0]["layer_index"], 1)
        self.assertEqual(result["matches"][0]["layer_name"], "Artwork")
        self.assertFalse(self.bridge.find_objects(layer_name="Art")["matches"])

    def test_literal_filters_and_unicode_casefold(self):
        self.assertEqual(len(self.bridge.find_objects(text_contains="STRASSE")["matches"]), 1)
        self.assertEqual(self.bridge.find_objects(name_contains=".*")["matches"], [])
        self.assertEqual(len(self.bridge.find_objects(text_contains="Member")["matches"]), 3)

    def test_case_sensitive_applies_to_all_string_filters(self):
        self.assertEqual(self.bridge.find_objects(name_contains="title", case_sensitive=True)["matches"], [])
        self.assertEqual(self.bridge.find_objects(layer_name="artwork", case_sensitive=True)["matches"], [])
        self.assertEqual(self.bridge.find_objects(text_contains="member", case_sensitive=True)["matches"], [])
        self.assertEqual(len(self.bridge.find_objects(name_contains="TITLE", case_sensitive=True)["matches"]), 3)

    def test_top_level_search_intentionally_omits_children(self):
        result = self.bridge.find_objects(include_nested=False)
        self.assertEqual([m["static_id"] for m in result["matches"]], [101, 102, 201])
        self.assertFalse(result["truncated"])

    def test_depth_limit_reports_incomplete_descendant_coverage(self):
        result = self.bridge.find_objects(page_index=1, max_depth=1)
        self.assertEqual([m["static_id"] for m in result["matches"]], [101, 102, 103, 104])
        self.assertEqual(result["incomplete_reasons"], ["max_depth"])
        self.assertTrue(result["truncated"])
        self.assertEqual(self.bridge.find_objects(max_depth=0)["scanned_objects"], 3)

    def test_result_limit_needs_an_extra_matching_object_to_prove_truncation(self):
        exact = self.bridge.find_objects(name_contains="TITLE", max_results=3)
        self.assertFalse(exact["truncated"])
        limited = self.bridge.find_objects(name_contains="TITLE", max_results=2)
        self.assertEqual([m["static_id"] for m in limited["matches"]], [101, 103])
        self.assertEqual(limited["incomplete_reasons"], ["max_results"])
        self.assertTrue(limited["truncated"])

    def test_exact_scan_budget_is_complete_but_one_less_is_incomplete(self):
        complete = self.bridge.find_objects(max_scan=11)
        self.assertFalse(complete["truncated"])
        limited = self.bridge.find_objects(max_scan=10)
        self.assertEqual(limited["scanned_entries"], 10)
        self.assertEqual(limited["incomplete_reasons"], ["max_scan"])
        self.assertEqual(len(limited["matches"]), 5)

    def test_empty_pages_and_nonmatching_layers_also_consume_the_budget(self):
        pages = _Collection(*(_page(_layer("Not matched")) for _ in range(100)))
        self.document.Pages = pages
        result = self.bridge.find_objects(layer_name="Artwork", max_scan=7)
        self.assertEqual(result["scanned_entries"], 7)
        self.assertEqual(result["scanned_objects"], 0)
        self.assertEqual(result["incomplete_reasons"], ["max_scan"])
        self.assertEqual(pages.reads, 4)

    def test_nonmatching_shapes_cannot_bypass_the_scan_budget(self):
        shapes = self.front.AllLayers.items[0].Shapes
        shapes.items = [_shape("Not matched", n) for n in range(100)]
        result = self.bridge.find_objects(name_contains="absent", page_index=1, max_scan=7)
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["scanned_objects"], 5)
        self.assertEqual(shapes.reads, 5)
        self.assertTrue(result["truncated"])

    def test_group_cycle_is_skipped_and_reported(self):
        group = self.front.AllLayers.items[0].Shapes.items[1]
        group.Shapes.items.append(group)
        result = self.bridge.find_objects(page_index=1)
        self.assertEqual([m["static_id"] for m in result["matches"]], [101, 102, 103, 104, 105])
        self.assertEqual(result["incomplete_reasons"], ["cycle"])
        self.assertTrue(result["truncated"])

    def test_page_layers_fallback_and_master_layer_locations(self):
        del self.front.AllLayers
        master = _layer("Master", _shape("Shared", 301))
        self.front.Layers.items.append(master)
        self.back.AllLayers.items.append(master)
        result = self.bridge.find_objects(layer_name="Master")
        self.assertEqual([m["page_index"] for m in result["matches"]], [1, 2])
        self.assertEqual([m["static_id"] for m in result["matches"]], [301, 301])

    def test_invalid_page_is_reported_even_when_no_layer_matches(self):
        with self.assertRaises(CorelBridgeError) as caught:
            self.bridge.find_objects(page_index=3, layer_name="Absent")
        self.assertEqual(caught.exception.code, ErrorCode.OBJECT_NOT_FOUND)
        self.assertEqual(caught.exception.details["page_count"], 2)

    def test_output_strings_are_bounded_after_full_literal_matching(self):
        self.first.Name = "a" * 256 + "needle"
        self.first.Text.Story.Text = "b" * 160 + "tail"
        self.front.AllLayers.items[0].Name = "l" * 257
        match = self.bridge.find_objects(name_contains="needle", text_contains="tail")["matches"][0]
        self.assertEqual(len(match["object_name"]), 256)
        self.assertTrue(match["name_truncated"])
        self.assertEqual(len(match["text_preview"]), 160)
        self.assertTrue(match["text_truncated"])
        self.assertEqual(len(match["layer_name"]), 256)
        self.assertTrue(match["layer_name_truncated"])

    def test_missing_static_id_has_no_fabricated_edit_identity(self):
        del self.first.StaticID
        match = self.bridge.find_objects(text_contains="Alice")["matches"][0]
        self.assertIsNone(match["static_id"])
        self.assertIsNone(match["object_id"])
        self.assertEqual(match["shape_path"], [1])

    def test_unbound_search_refuses_without_connecting(self):
        self.bridge.target_doc = None
        with patch.object(self.bridge, "connect", side_effect=AssertionError("must not connect")):
            with self.assertRaises(CorelBridgeError) as caught:
                self.bridge.find_objects()
        self.assertEqual(caught.exception.code, ErrorCode.NO_TARGET_DOCUMENT)

    def test_invalid_arguments_fail_before_document_access(self):
        invalid = (
            {"name_contains": None}, {"name_contains": "a" * 257},
            {"text_contains": "a" * 1025}, {"layer_name": "a" * 257},
            {"shape_type_code": True}, {"shape_type_code": -1},
            {"page_index": 0}, {"page_index": True}, {"page_index": 1.0},
            {"max_results": 0}, {"max_results": 1001}, {"max_results": True},
            {"max_depth": -1}, {"max_depth": 17}, {"max_depth": 1.0},
            {"max_scan": 0}, {"max_scan": 10001}, {"max_scan": False},
            {"include_nested": 1}, {"case_sensitive": "false"},
        )
        with patch.object(self.bridge, "_target_document", side_effect=AssertionError("must not access")):
            for kwargs in invalid:
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(CorelBridgeError) as caught:
                        self.bridge.find_objects(**kwargs)
                    self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_com_failure_does_not_return_a_partial_success_or_raw_details(self):
        class _BrokenShape:
            @property
            def Name(self):
                raise RuntimeError("private COM detail")

        self.front.AllLayers.items[0].Shapes.items.append(_BrokenShape())
        with self.assertRaises(CorelBridgeError) as caught:
            self.bridge.find_objects(page_index=1)
        self.assertEqual(caught.exception.code, ErrorCode.COREL_COM_ERROR)
        self.assertNotIn("private", str(caught.exception))

    def test_actual_complete_and_incomplete_results_match_catalog_schema(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / "catalog" / "mcp_tool_registry.json").read_text(encoding="utf-8"))
        tool = next(t for t in registry["tools"] if t["name"] == "find_objects")
        validator = Draft202012Validator({
            "schema_definitions": registry["schema_definitions"],
            "allOf": [tool["output_schema"]],
        })
        for kwargs in ({}, {"max_scan": 3}, {"max_results": 1}, {"max_depth": 0}):
            with self.subTest(kwargs=kwargs):
                validator.validate(success_result("find_objects", self.bridge.find_objects(**kwargs), 0.1))


if __name__ == "__main__":
    unittest.main()
