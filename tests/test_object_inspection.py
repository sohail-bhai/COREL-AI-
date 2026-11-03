from __future__ import annotations

import copy
import json
import unittest

from fake_documents import attach_open_document
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

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


class _Broken:
    def __getattr__(self, name):
        raise RuntimeError("Private client content C:/private/client.cdr token=secret")


class ObjectInspectionTests(unittest.TestCase):
    def setUp(self):
        self.story = SimpleNamespace(
            Text="Hello\r\nनमस्ते", Font="Arial", Size=18.0, Bold=-1,
            Italic=0, Underline=0, Alignment=1,
        )
        self.color = SimpleNamespace(
            Type=5, Name="RGB", HexValue="0A141E", RGBRed=10, RGBGreen=20, RGBBlue=30,
        )
        self.shape = SimpleNamespace(
            Name="headline", StaticID=101, Type=6, PositionX=-1.25, PositionY=2.5,
            SizeWidth=3.0, SizeHeight=0.5, Text=SimpleNamespace(Story=self.story),
            Fill=SimpleNamespace(Type=1, UniformColor=self.color),
            Layer=SimpleNamespace(Name="Artwork"), Page=SimpleNamespace(Index=1),
        )
        self.page = SimpleNamespace(Shapes=_Collection(self.shape))
        self.document = SimpleNamespace(
            Name="Target.cdr", ActivePage=self.page, Unit=3, ReferencePoint=9, Dirty=False,
        )
        self.other = SimpleNamespace(Name="Client.cdr", ActivePage=_Broken())
        self.bridge = CorelBridge()
        self.bridge.app = SimpleNamespace(ActiveDocument=self.other)
        attach_open_document(self.bridge, self.document)

    def assert_error(self, code, method, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            getattr(self.bridge, method)(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        return caught.exception

    def test_bounds_restore_context_and_explain_coordinates(self):
        result = self.bridge.get_object_bounds(object_name="headline")
        self.assertEqual(result["unit"], "inch")
        self.assertEqual(result["bounds"]["lower_left"], {"x": -1.25, "y": 2.5})
        self.assertEqual(result["bounds"]["upper_right"], {"x": 1.75, "y": 3.0})
        self.assertEqual(result["bounds"]["center"], {"x": 0.25, "y": 2.75})
        self.assertEqual(result["bounds"]["coordinate_space"], "document_ruler_bottom_left_reference")
        self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))

    def test_geometry_is_read_under_inch_bottom_left_context(self):
        document = self.document

        class Shape:
            def __getattr__(inner, name):
                self.assertEqual((document.Unit, document.ReferencePoint), (1, 5))
                return {"PositionX": 1, "PositionY": 2, "SizeWidth": 3, "SizeHeight": 4}[name]

        with patch.object(self.bridge, "_inspection_target", return_value=(document, Shape(), {})):
            self.assertEqual(self.bridge.get_object_bounds(shape_index=1)["bounds"]["width"], 3)
        self.assertEqual((document.Unit, document.ReferencePoint), (3, 9))

    def test_failed_or_nonfinite_bounds_never_report_success_and_restore_context(self):
        for value in (None, float("nan"), float("inf"), -1):
            with self.subTest(value=value):
                self.shape.SizeWidth = value
                self.assert_error(ErrorCode.COREL_COM_ERROR, "get_object_bounds", shape_index=1)
                self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))

    def test_restoration_failure_is_an_error_and_other_context_still_restores(self):
        original = self.document

        class Document:
            Unit = 3
            ActivePage = original.ActivePage
            Name = original.Name
            point = 9

            @property
            def ReferencePoint(inner):
                return inner.point

            @ReferencePoint.setter
            def ReferencePoint(inner, value):
                if value == 9:
                    raise RuntimeError("secret")
                inner.point = value

        document = Document()
        attach_open_document(self.bridge, document)
        error = self.assert_error(ErrorCode.COREL_COM_ERROR, "get_object_bounds", shape_index=1)
        self.assertIn("restore", str(error))
        self.assertEqual(document.Unit, 3)

    def test_overflowing_derived_bounds_are_rejected(self):
        self.shape.PositionX = 1e308
        self.shape.SizeWidth = 1e308
        self.assert_error(ErrorCode.COREL_COM_ERROR, "get_object_bounds", shape_index=1)
        self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))

    def test_text_reports_actual_aggregate_properties(self):
        result = self.bridge.get_text_properties(object_name="headline")
        text = result["text"]
        self.assertEqual(text["content"], self.story.Text)
        self.assertEqual(text["content_length"], len(self.story.Text))
        self.assertFalse(text["content_truncated"])
        self.assertEqual(text["font"], "Arial")
        self.assertEqual(text["size_points"], 18)
        self.assertTrue(text["bold"])
        self.assertFalse(text["italic"])
        self.assertEqual(text["formatting_scope"], "whole_story_aggregate")
        self.assertEqual(text["unavailable_properties"], [])
        self.assertEqual(text["indeterminate_properties"], [])

    def test_unicode_content_truncation_and_metadata_only_read_are_explicit(self):
        for limit in (0, 1, 8, len(self.story.Text)):
            with self.subTest(limit=limit):
                text = self.bridge.get_text_properties(shape_index=1, max_text_chars=limit)["text"]
                self.assertEqual(text["content"], self.story.Text[:limit])
                self.assertEqual(text["content_length"], len(self.story.Text))
                self.assertEqual(text["content_truncated"], len(self.story.Text) > limit)
        self.story.Text = "x" * 10001
        self.assertEqual(len(self.bridge.get_text_properties(shape_index=1)["text"]["content"]), 2000)
        self.assertEqual(len(self.bridge.get_text_properties(shape_index=1, max_text_chars=10000)["text"]["content"]), 10000)

    def test_empty_text_is_available_and_not_truncated(self):
        self.story.Text = ""
        text = self.bridge.get_text_properties(shape_index=1, max_text_chars=0)["text"]
        self.assertEqual(text["content"], "")
        self.assertFalse(text["content_truncated"])

    def test_undefined_formatting_is_not_reported_as_false_or_uniform(self):
        self.story.Bold = -2
        self.story.Italic = -2
        self.story.Font = ""
        self.story.Size = 0
        self.story.Underline = -2
        self.story.Alignment = -2
        text = self.bridge.get_text_properties(shape_index=1)["text"]
        self.assertIsNone(text["bold"])
        self.assertIsNone(text["italic"])
        self.assertIsNone(text["font"])
        self.assertIsNone(text["size_points"])
        self.assertEqual(text["bold_code"], -2)
        self.assertCountEqual(text["indeterminate_properties"], [
            "font", "size_points", "bold_code", "italic_code", "underline_code", "alignment_code",
        ])
        self.assertIsNone(self.bridge._text_readback(self.shape)["bold"])

    def test_unavailable_formatting_does_not_hide_readable_content(self):
        self.shape.Text.Story = SimpleNamespace(Text="Readable")
        text = self.bridge.get_text_properties(shape_index=1)["text"]
        self.assertEqual(text["content"], "Readable")
        self.assertIsNone(text["bold"])
        self.assertCountEqual(text["unavailable_properties"], [
            "font", "size_points", "bold_code", "italic_code", "underline_code", "alignment_code",
        ])

    def test_nonfinite_font_size_is_unavailable(self):
        self.story.Size = float("nan")
        text = self.bridge.get_text_properties(shape_index=1)["text"]
        self.assertIsNone(text["size_points"])
        self.assertIn("size_points", text["unavailable_properties"])
        json.dumps(text, allow_nan=False)

    def test_non_text_shape_is_rejected_before_story_access(self):
        self.shape.Type = 1
        self.shape.Text = _Broken()
        self.assert_error(ErrorCode.INVALID_ARGUMENT, "get_text_properties", shape_index=1)

    def test_unavailable_shape_type_is_not_misreported_as_non_text(self):
        self.shape.Type = None
        self.assert_error(ErrorCode.COREL_COM_ERROR, "get_text_properties", shape_index=1)

    def test_unavailable_story_or_content_returns_sanitized_com_error(self):
        for story in (_Broken(), SimpleNamespace(Text=None)):
            self.shape.Text.Story = story
            self.assert_error(ErrorCode.COREL_COM_ERROR, "get_text_properties", shape_index=1)

    def test_fill_preserves_rgb_and_cmyk_without_conversion(self):
        result = self.bridge.get_fill(shape_index=1)["fill"]
        self.assertEqual(result["color"]["model"], "rgb")
        self.assertEqual(result["color"]["value"], {"red": 10, "green": 20, "blue": 30})
        self.shape.Fill.UniformColor = SimpleNamespace(
            Type=2, CMYKCyan=10, CMYKMagenta=20, CMYKYellow=30, CMYKBlack=40,
        )
        result = self.bridge.get_fill(shape_index=1)["fill"]
        self.assertEqual(result["color"]["model"], "cmyk")
        self.assertEqual(result["color"]["value"], {"cyan": 10, "magenta": 20, "yellow": 30, "black": 40})
        self.assertEqual(result["unavailable_properties"], [])

    def test_none_nonuniform_and_unknown_fills_do_not_probe_uniform_color(self):
        for type_code, expected in ((0, "none"), (2, "fountain"), (987, "unknown")):
            self.shape.Fill = SimpleNamespace(Type=type_code)
            fill = self.bridge.get_fill(shape_index=1)["fill"]
            self.assertEqual(fill["type"], expected)
            self.assertIsNone(fill["color"])
            self.assertEqual(fill["detail_scope"], "type_and_uniform_color")

    def test_missing_uniform_color_and_channels_are_explicit(self):
        self.shape.Fill.UniformColor = None
        self.assertEqual(self.bridge.get_fill(shape_index=1)["fill"]["unavailable_properties"], ["color"])
        self.shape.Fill.UniformColor = SimpleNamespace(Type=5, RGBRed=10, RGBGreen=20)
        fill = self.bridge.get_fill(shape_index=1)["fill"]
        self.assertIsNone(fill["color"]["value"]["blue"])
        self.assertEqual(fill["unavailable_properties"], ["color.value.blue"])

    def test_unknown_color_model_is_retained_without_rgb_guessing(self):
        self.color.Type = 987
        fill = self.bridge.get_fill(shape_index=1)["fill"]
        self.assertEqual(fill["color"]["model"], "unknown")
        self.assertEqual(fill["color"]["type_code"], 987)
        self.assertIsNone(fill["color"]["value"])

    def test_gray_and_spot_fills_retain_native_channels_and_tint(self):
        for color, model, value in (
            (SimpleNamespace(Type=9, Gray=128), "gray", {"gray": 128}),
            (SimpleNamespace(Type=25, SpotColorName="Brand Ink", Tint=65), "spot",
             {"spot_name": "Brand Ink", "tint": 65}),
        ):
            self.shape.Fill.UniformColor = color
            fill = self.bridge.get_fill(shape_index=1)["fill"]
            self.assertEqual(fill["color"]["model"], model)
            self.assertEqual(fill["color"]["value"], value)

    def test_long_font_and_native_color_names_are_bounded_and_reported(self):
        self.story.Font = "F" * 257
        text = self.bridge.get_text_properties(shape_index=1)["text"]
        self.assertEqual(len(text["font"]), 256)
        self.assertEqual(text["truncated_properties"], ["font"])
        self.shape.Fill.UniformColor = SimpleNamespace(
            Type=25, Name="N" * 257, HexValue="H" * 257, SpotColorName="S" * 257, Tint=100,
        )
        fill = self.bridge.get_fill(shape_index=1)["fill"]
        self.assertEqual(len(fill["color"]["name"]), 256)
        self.assertEqual(len(fill["color"]["hex_value"]), 256)
        self.assertEqual(len(fill["color"]["value"]["spot_name"]), 256)
        self.assertCountEqual(fill["truncated_properties"], [
            "color.name", "color.hex_value", "color.value.spot_name",
        ])

    def test_missing_fill_type_returns_sanitized_com_error(self):
        self.shape.Fill = _Broken()
        self.assert_error(ErrorCode.COREL_COM_ERROR, "get_fill", shape_index=1)

    def test_all_readers_return_same_actual_identity_and_preserve_artwork(self):
        before = copy.deepcopy(vars(self.shape))
        identities = []
        for method in ("get_object_bounds", "get_text_properties", "get_fill"):
            result = getattr(self.bridge, method)(object_name="headline")
            self.assertEqual(result["document_name"], "Target.cdr")
            identities.append(result["object"])
            self.assertIs(self.bridge.app.ActiveDocument, self.other)
            self.assertFalse(self.document.Dirty)
            self.assertEqual(vars(self.shape), before)
            self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))
        self.assertEqual(identities[0], identities[1])
        self.assertEqual(identities[1], identities[2])
        self.assertEqual(identities[0]["object_id"], "doc-0001:shape:101")
        self.assertEqual(identities[0]["shape_index"], 1)

    def test_missing_static_id_does_not_fabricate_an_object_id(self):
        del self.shape.StaticID
        identity = self.bridge.get_fill(shape_index=1)["object"]
        self.assertIsNone(identity["static_id"])
        self.assertIsNone(identity["object_id"])

    def test_index_inspection_caps_long_identity_summaries(self):
        self.shape.Name = "N" * 257
        self.shape.Layer.Name = "L" * 257
        identity = self.bridge.get_fill(shape_index=1)["object"]
        self.assertEqual(len(identity["object_name"]), 256)
        self.assertEqual(len(identity["layer_name"]), 256)
        self.assertTrue(identity["object_name_truncated"])
        self.assertTrue(identity["layer_name_truncated"])

    def test_unbound_readers_do_not_connect_or_bind_active_document(self):
        self.bridge.target_doc = None
        with patch.object(self.bridge, "connect", side_effect=AssertionError("Unexpected connect")):
            for method in ("get_object_bounds", "get_text_properties", "get_fill"):
                self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, method, shape_index=1)
        self.assertIsNone(self.bridge.target_doc)

    def test_invalid_selectors_and_text_limits_fail_before_document_access(self):
        with patch.object(self.bridge, "_target_document", side_effect=AssertionError("Unexpected COM")):
            for method in ("get_object_bounds", "get_text_properties", "get_fill"):
                for name, index, code in (
                    ("", 0, ErrorCode.AMBIGUOUS_SELECTOR),
                    ("headline", 1, ErrorCode.AMBIGUOUS_SELECTOR),
                    (" ", 0, ErrorCode.INVALID_ARGUMENT),
                    (None, 1, ErrorCode.INVALID_ARGUMENT),
                    ("x" * 257, 0, ErrorCode.INVALID_ARGUMENT),
                    ("", True, ErrorCode.INVALID_ARGUMENT),
                    ("", 1.5, ErrorCode.INVALID_ARGUMENT),
                    ("", "1", ErrorCode.INVALID_ARGUMENT),
                    ("", -1, ErrorCode.INVALID_ARGUMENT),
                ):
                    with self.subTest(method=method, name=name, index=index):
                        self.assert_error(code, method, object_name=name, shape_index=index)
            for limit in (-1, 10001, True, 1.5, "10", None):
                self.assert_error(ErrorCode.INVALID_ARGUMENT, "get_text_properties", shape_index=1, max_text_chars=limit)

    def test_duplicate_names_refuse_ambiguous_lookup_but_explicit_index_works(self):
        second = copy.deepcopy(self.shape)
        second.StaticID = 102
        self.page.Shapes.items.append(second)
        for method in ("get_object_bounds", "get_text_properties", "get_fill"):
            self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR, method, object_name="headline")
            self.assertEqual(getattr(self.bridge, method)(shape_index=2)["object"]["static_id"], 102)

    def test_missing_or_other_page_objects_are_not_fallback_targets(self):
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND, "get_fill", object_name="missing")
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND, "get_fill", shape_index=2)
        self.document.ActivePage = SimpleNamespace(Shapes=_Collection())
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND, "get_fill", object_name="headline")

    def test_nested_children_are_not_implicitly_selected(self):
        self.page.Shapes = _Collection(SimpleNamespace(Name="group", Shapes=_Collection(self.shape), Type=7))
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND, "get_fill", object_name="headline")

    def test_large_page_name_lookup_refuses_to_claim_uniqueness(self):
        shape = self.shape

        class Collection:
            Count = 10001
            reads = 0

            def Item(inner, index):
                inner.reads += 1
                return shape

        self.page.Shapes = collection = Collection()
        self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR, "get_fill", object_name="headline")
        self.assertEqual(collection.reads, 0)
        self.bridge.get_fill(shape_index=1)
        self.assertEqual(collection.reads, 1)

    def test_failed_name_enumeration_is_not_misreported_as_absence(self):
        self.page.Shapes = _Collection(_Broken())
        self.assert_error(ErrorCode.COREL_COM_ERROR, "get_fill", object_name="headline")

    def test_actual_results_match_strict_catalog_schemas(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / "catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        tools = {tool["name"]: tool for tool in registry["tools"]}
        for method in ("get_object_bounds", "get_text_properties", "get_fill"):
            schema = {"schema_definitions": registry["schema_definitions"], **tools[method]["output_schema"]}
            result = success_result(method, getattr(self.bridge, method)(shape_index=1), 0)
            Draft202012Validator(schema).validate(result)
            json.dumps(result, allow_nan=False)

    def test_required_readback_and_completeness_fields_cannot_disappear(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / "catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        tools = {tool["name"]: tool for tool in registry["tools"]}
        for method, section, field in (
            ("get_object_bounds", "bounds", "coordinate_space"),
            ("get_text_properties", "text", "content_truncated"),
            ("get_text_properties", "text", "indeterminate_properties"),
            ("get_fill", "fill", "unavailable_properties"),
        ):
            schema = {"schema_definitions": registry["schema_definitions"], **tools[method]["output_schema"]}
            result = success_result(method, getattr(self.bridge, method)(shape_index=1), 0)
            del result["data"][section][field]
            with self.assertRaises(ValidationError):
                Draft202012Validator(schema).validate(result)

    def test_catalog_inputs_reject_invalid_names_types_limits_and_unknown_fields(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / "catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        tools = {tool["name"]: tool for tool in registry["tools"]}
        for method in ("get_object_bounds", "get_text_properties", "get_fill"):
            schema = {"schema_definitions": registry["schema_definitions"], **tools[method]["input_schema"]}
            validator = Draft202012Validator(schema)
            validator.validate({"object_name": "headline"})
            validator.validate({"shape_index": 1})
            for arguments in (
                {}, {"object_name": " "}, {"object_name": "x" * 257}, {"shape_index": True},
                {"shape_index": -1}, {"shape_index": 1.5}, {"shape_index": 1, "macro": "unsafe"},
                {"object_name": "headline", "shape_index": 1},
            ):
                with self.assertRaises(ValidationError):
                    validator.validate(arguments)
            if method == "get_text_properties":
                for limit in (-1, 10001, True, 1.5):
                    with self.assertRaises(ValidationError):
                        validator.validate({"shape_index": 1, "max_text_chars": limit})


if __name__ == "__main__":
    unittest.main()
