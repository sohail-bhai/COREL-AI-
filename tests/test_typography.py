from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result
from fake_documents import attach_open_document


class Collection:
    def __init__(self, *items):
        self.items = list(items)
        self.reads = []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        self.reads.append(index)
        value = self.items[index - 1]
        if isinstance(value, Exception):
            raise value
        return value


class Story:
    def __init__(self, text="Hello नमस्ते", **formatting):
        self.__dict__.update(Text=text, Font="Arial", Size=12., Bold=False, Italic=False,
                             Underline=0, Alignment=1, CharSpacing=0., WordSpacing=100.,
                             LineSpacing=100., LineSpacingType=0, writes=[], fail_on=None,
                             substitute_font=None, **formatting)

    def __setattr__(self, attr, value):
        if attr in ("Font", "Size", "Bold", "Italic", "Underline", "Alignment"):
            self.writes.append((attr, value))
            if attr == "Font" and self.substitute_font:
                value = self.substitute_font
            self.__dict__[attr] = value
            if attr == self.fail_on:
                raise RuntimeError("Private path C:/client/secret.cdr")
        else:
            self.__dict__[attr] = value


class TypographyTests(unittest.TestCase):
    def setUp(self):
        self.story = Story()
        self.shape = SimpleNamespace(Name="Title", StaticID=101, Type=6,
            Text=SimpleNamespace(Story=self.story, Type=0, Overflow=False, Frames=Collection(object())),
            PositionX=1., PositionY=2., SizeWidth=3., SizeHeight=0.5)
        self.layer = SimpleNamespace(Name="Artwork", Shapes=Collection(self.shape))
        self.page = SimpleNamespace(Index=1, Shapes=Collection(self.shape), AllLayers=Collection(self.layer),
                                    ActiveLayer=self.layer)
        self.shape.Page, self.shape.Layer = self.page, self.layer
        self.document = SimpleNamespace(Name="Target.cdr", Pages=Collection(self.page), ActivePage=self.page,
                                        Unit=3, ReferencePoint=9, Dirty=False)
        self.fonts = Collection("Arial", "Times New Roman", "Noto Sans")
        self.bridge = CorelBridge()
        self.bridge.app = SimpleNamespace(FontList=self.fonts)
        attach_open_document(self.bridge, self.document)
        self.create_calls = []
        def create(*args):
            self.create_calls.append(args)
            left, top, right, bottom, content, _, _, font, size, bold, italic, underline, align = args
            story = Story(content.replace("\r\n", "\r").replace("\n", "\r"))
            story.__dict__.update(Font=font, Size=size, Bold=bool(bold), Italic=bool(italic),
                                  Underline=underline, Alignment=align)
            shape = SimpleNamespace(Name="", StaticID=102, Type=6, Page=self.page, Layer=self.layer,
                                    PositionX=left, PositionY=bottom, SizeWidth=right-left, SizeHeight=top-bottom,
                                    Text=SimpleNamespace(Story=story, Type=1, Overflow=True, Frames=Collection(object())))
            self.page.Shapes.items.append(shape)
            self.layer.Shapes.items.append(shape)
            return shape
        self.layer.CreateParagraphText = create

    def error(self, code, function, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            function(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("secret", str(caught.exception))
        return caught.exception

    def test_font_search_is_literal_case_insensitive_and_exact_limit_is_complete(self):
        value = self.bridge.list_fonts("a", max_results=3)
        self.assertEqual(value["fonts"], ["Arial", "Times New Roman", "Noto Sans"])
        self.assertFalse(value["truncated"])
        self.assertEqual(self.bridge.list_fonts(".*")["fonts"], [])

    def test_font_search_proves_truncation_with_extra_match(self):
        value = self.bridge.list_fonts(max_results=1)
        self.assertEqual(value["incomplete_reasons"], ["max_results"])
        self.assertEqual(value["scanned_count"], 2)
        self.assertEqual(self.bridge.list_fonts(max_scan=1)["incomplete_reasons"], ["max_scan"])

    def test_unreadable_font_entries_make_search_incomplete(self):
        self.fonts.items.insert(0, RuntimeError("secret"))
        self.assertEqual(self.bridge.list_fonts("Missing")["incomplete_reasons"], ["unavailable_font_entry"])
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, self.bridge.set_text_style, font="Arial", object_name="Title")
        self.assertFalse(self.story.writes)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_font_availability_is_complete_beyond_default_result_count(self):
        self.fonts.items = [f"Font{i}" for i in range(1200)] + ["Arial"]
        self.assertEqual(self.bridge._require_font("arial"), "Arial")
        self.assertEqual(len(self.fonts.reads), 1201)

    def test_oversized_font_catalog_is_refused_before_edit(self):
        self.fonts.items = ["Other"] * 10001
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, self.bridge.set_text_style, font="Arial", object_name="Title")
        self.assertLessEqual(len(self.fonts.reads), 10000)
        self.assertFalse(self.story.writes)

    def test_missing_font_is_preflight_and_does_not_change_other_requested_properties(self):
        self.error(ErrorCode.INVALID_ARGUMENT, self.bridge.set_text_style, font="Missing", bold=True, object_name="Title")
        self.assertFalse(self.story.writes)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_style_changes_formatting_without_stretching_or_replacing_content(self):
        content = self.story.Text
        value = self.bridge.set_text_style(font="arial", size_points=24, bold=True, italic=True,
                                           underline="single", alignment="center", object_name="Title")
        self.assertEqual(value["requested_style"]["font"], "Arial")
        self.assertEqual(value["actual_style"]["size_points"], 24)
        self.assertFalse(value["before_style"]["bold"])
        self.assertTrue(value["actual_style"]["bold"])
        self.assertEqual(value["actual_style"]["alignment"], "center")
        self.assertEqual(self.story.Text, content)
        self.assertEqual((self.shape.SizeWidth, self.shape.SizeHeight), (3., .5))
        self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))
        self.assertIsNotNone(value["object"]["object_reference"])

    def test_null_properties_are_preserved_and_no_font_lookup_is_needed(self):
        self.bridge.app.FontList = None
        value = self.bridge.set_text_style(bold=False, object_name="Title")
        self.assertEqual(self.story.writes, [("Bold", False)])
        self.assertEqual(value["actual_style"]["font"], "Arial")

    def test_mixed_style_can_be_replaced_with_explicit_uniform_values(self):
        self.story.__dict__.update(Font="", Size=0, Underline=7, Alignment=6)
        value = self.bridge.set_text_style(font="Arial", size_points=18, underline="none", alignment="left", shape_index=1)
        self.assertIsNone(value["before_style"]["font"])
        self.assertEqual(value["actual_style"]["unavailable_or_mixed_properties"], [])

    def test_nontext_fitted_linked_and_unknown_targets_are_refused(self):
        self.shape.Type = 1
        self.error(ErrorCode.INVALID_ARGUMENT, self.bridge.set_text_style, bold=True, shape_index=1)
        self.shape.Type = 6
        for code, frames in ((2, 1), (3, 1), (0, 2), (1, 2), (9, 1), (1, 0)):
            self.shape.Text.Type, self.shape.Text.Frames = code, Collection(*[object() for _ in range(frames)])
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, self.bridge.set_text_style, bold=True, shape_index=1)
        self.assertFalse(self.story.writes)

    def test_signed_reference_survives_reordering_but_refuses_replacement(self):
        reference = self.bridge.get_text_properties(shape_index=1)["object"]["object_reference"]
        self.page.Shapes.items.insert(0, SimpleNamespace(Name="Other", Type=1, StaticID=999))
        self.bridge.set_text_style(bold=True, object_reference=reference)
        self.assertTrue(self.story.Bold)
        replacement = copy.copy(self.shape)
        self.layer.Shapes.items = [replacement]
        self.page.Shapes.items[1] = replacement
        self.error(ErrorCode.OBJECT_NOT_FOUND, self.bridge.set_text_style, italic=True, object_reference=reference)
        self.assertFalse(self.story.Italic)

    def test_reference_mutation_requires_explicitly_active_page(self):
        reference = self.bridge.get_text_properties(shape_index=1)["object"]["object_reference"]
        other = SimpleNamespace(Index=2, Shapes=Collection(), AllLayers=Collection())
        self.document.Pages.items.append(other)
        self.document.ActivePage = other
        self.error(ErrorCode.INVALID_ARGUMENT, self.bridge.set_text_style, bold=True, object_reference=reference)
        self.assertFalse(self.story.writes)

    def test_partial_write_failure_is_tracked_and_error_is_redacted(self):
        self.story.fail_on = "Size"
        self.error(ErrorCode.COREL_COM_ERROR, self.bridge.set_text_style, font="Noto Sans", size_points=20, object_name="Title")
        self.assertEqual(self.story.Font, "Noto Sans")
        self.assertTrue(self.bridge._operation_mutation_started)

    def test_partial_style_failure_blocks_followup_worker_mutations(self):
        self.story.fail_on = "Size"
        with patch.object(server, "CorelBridge", return_value=self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, "dispatcher", dispatcher):
                failed = server.set_text_style(font="Noto Sans", size_points=20, object_name="Title")
                self.assertEqual(failed["error"]["code"], "COREL_COM_ERROR")
                self.assertEqual(server.set_text_style(bold=True, object_name="Title")["error"]["code"], "RECOVERY_REQUIRED")
                self.assertTrue(server.list_fonts()["ok"])
        finally:
            dispatcher.close()

    def test_font_substitution_and_unavailable_actual_bounds_are_errors(self):
        self.story.substitute_font = "Other"
        self.error(ErrorCode.COREL_COM_ERROR, self.bridge.set_text_style, font="Arial", object_name="Title")
        self.story.substitute_font = None
        self.shape.SizeWidth = float("nan")
        self.error(ErrorCode.COREL_COM_ERROR, self.bridge.set_text_style, size_points=20, object_name="Title")

    def test_paragraph_signature_frame_coordinates_charset_and_readback(self):
        value = self.bridge.add_paragraph_text("First\nनमस्ते", -1, 2, 3, 4, size_points=18,
            font="Times New Roman", bold=True, italic=False, underline="single", alignment="justify", object_name="Body")
        args = self.create_calls[0]
        self.assertEqual(args[:4], (-1., 6., 2., 2.))
        self.assertEqual(args[5:7], (0, -1))
        self.assertEqual(args[9:], (-1, 0, 1, 4))
        self.assertEqual(value["actual_bounds_inches"], {"x": -1., "y": 2., "width": 3., "height": 4.})
        self.assertTrue(value["line_breaks_normalized"])
        self.assertEqual(value["layout"]["text_type"], "paragraph")
        self.assertTrue(value["layout"]["overflow"])
        self.assertIsNotNone(value["object"]["object_reference"])
        self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))

    def test_paragraph_preflight_and_creation_failure_stage(self):
        self.error(ErrorCode.INVALID_ARGUMENT, self.bridge.add_paragraph_text, text="X", x_inches=1, y_inches=1,
                   width_inches=2, height_inches=2, font="Missing")
        self.assertFalse(self.create_calls)
        self.assertFalse(self.bridge._operation_mutation_started)
        def fail(*args):
            raise RuntimeError("secret")
        self.layer.CreateParagraphText = fail
        self.error(ErrorCode.COREL_COM_ERROR, self.bridge.add_paragraph_text, text="X", x_inches=1, y_inches=1,
                   width_inches=2, height_inches=2)
        self.assertTrue(self.bridge._operation_mutation_started)
        self.assertEqual(self.document.Unit, 3)

    def test_layout_reports_story_overflow_and_unavailable_metadata(self):
        self.shape.Text.Type, self.shape.Text.Overflow = 1, True
        self.shape.Text.Frames = Collection(object(), object())
        layout = self.bridge.get_text_properties(shape_index=1)["text"]["layout"]
        self.assertTrue(layout["overflow"])
        self.assertEqual(layout["overflow_scope"], "linked_story")
        self.assertEqual(layout["frame_count"], 2)
        del self.shape.Text.Overflow
        layout = self.bridge.get_text_properties(shape_index=1)["text"]["layout"]
        self.assertIsNone(layout["overflow"])
        self.assertIn("overflow", layout["unavailable_properties"])

    def test_invalid_inputs_are_refused_without_native_writes(self):
        for kwargs in ({}, {"bold": 1}, {"italic": "yes"}, {"font": " Arial"}, {"font": ""},
                       {"font": "x"*201}, {"size_points": True}, {"size_points": float("inf")},
                       {"size_points": 0}, {"size_points": 10**400}, {"alignment": "middle"}, {"underline": "double"}):
            self.error(ErrorCode.INVALID_ARGUMENT, self.bridge.set_text_style, object_name="Title", **kwargs)
        for kwargs in ({"max_results": True}, {"max_scan": 0}, {"name_contains": None}):
            self.error(ErrorCode.INVALID_ARGUMENT, self.bridge.list_fonts, **kwargs)
        for field, bad in (("text", ""), ("text", "x"*100001), ("width_inches", 0),
                           ("x_inches", float("nan")), ("object_name", "x\n")):
            kwargs = dict(text="Body", x_inches=1, y_inches=1, width_inches=2, height_inches=2)
            kwargs[field] = bad
            self.error(ErrorCode.INVALID_ARGUMENT, self.bridge.add_paragraph_text, **kwargs)
        self.assertFalse(self.story.writes)
        self.assertFalse(self.create_calls)

    def test_large_existing_font_sizes_have_valid_readback(self):
        self.story.__dict__["Size"] = 800
        value = self.bridge.set_text_style(bold=True, shape_index=1)
        registry = json.loads((Path(__file__).resolve().parents[1]/"catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        schema = {"schema_definitions": registry["schema_definitions"],
                  **next(tool for tool in registry["tools"] if tool["name"]=="set_text_style")["output_schema"]}
        Draft202012Validator(schema).validate(success_result("set_text_style", value, 1))

    def test_runtime_output_schemas_and_strict_inputs(self):
        registry = json.loads((Path(__file__).resolve().parents[1]/"catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        tools = {tool["name"]: tool for tool in registry["tools"]}
        results = {"list_fonts": self.bridge.list_fonts(),
                   "set_text_style": self.bridge.set_text_style(bold=True, shape_index=1),
                   "add_paragraph_text": self.bridge.add_paragraph_text("Body", 1, 2, 3, 4)}
        for name, result in results.items():
            schema = {"schema_definitions": registry["schema_definitions"], **tools[name]["output_schema"]}
            validator = Draft202012Validator(schema)
            validator.validate(success_result(name, result, 1))
            corrupted = copy.deepcopy(result)
            corrupted["unexpected"] = True
            with self.assertRaises(ValidationError):
                validator.validate(success_result(name, corrupted, 1))
        schema = {"schema_definitions": registry["schema_definitions"], **tools["set_text_style"]["input_schema"]}
        validator = Draft202012Validator(schema)
        validator.validate({"bold": True, "shape_index": 1})
        validator.validate({"bold": True, "object_reference": results["set_text_style"]["object"]["object_reference"]})
        for bad in ({"bold": True}, {"shape_index": 1}, {"bold": None, "shape_index": 1},
                    {"bold": True, "shape_index": 1, "object_name": "Title"},
                    {"bold": True, "shape_index": 1, "unknown": 1}):
            with self.assertRaises(ValidationError):
                validator.validate(bad)

    def test_server_tools_forward_optional_arguments(self):
        with patch.object(server, "_tool", return_value={}) as call:
            server.set_text_style(italic=True, object_name="Title")
            self.assertEqual(call.call_args.args, ("set_text_style", "set_text_style", None, None, None, True,
                                                   None, None, "Title", 0, None))
            server.list_fonts("Noto", 4, 20)
            self.assertEqual(call.call_args.args, ("list_fonts", "list_fonts", "Noto", 4, 20))


if __name__ == "__main__":
    unittest.main()
