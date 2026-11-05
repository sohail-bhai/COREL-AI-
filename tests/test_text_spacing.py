from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result
import test_typography as fixtures


class TextSpacingTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.TypographyTests()
        fixture.setUp()
        self.bridge, self.story, self.shape = fixture.bridge, fixture.story, fixture.shape
        self.page, self.document = fixture.page, fixture.document
        self.story.ParaSpacingBefore, self.story.ParaSpacingAfter = 4., 6.
        self.calls = []
        self.native_failure = False
        self.after_native = lambda: None

        def spacing(kind, line, before, after):
            self.calls.append((kind, line, before, after))
            self.story.__dict__.update(LineSpacingType=kind, LineSpacing=line,
                                      ParaSpacingBefore=before, ParaSpacingAfter=after)
            self.after_native()
            if self.native_failure:
                raise RuntimeError('Private text and C:/client/artwork.cdr')
        self.story.SetLineSpacing = spacing

    def edit(self, **kwargs):
        kwargs.setdefault('object_name', 'Title')
        return self.bridge.set_text_spacing(**kwargs)

    def error(self, code, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            self.edit(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn('Private', str(caught.exception))
        self.assertNotIn('artwork.cdr', str(caught.exception))

    def test_same_unit_preserves_null_values_and_content(self):
        prior = self.story.Text
        result = self.edit(line_spacing=125)
        self.assertEqual(self.calls, [(0, 125., 4., 6.)])
        self.assertEqual(result['requested_spacing'], {'line_spacing': 125.})
        self.assertTrue(result['content_preserved'])
        self.assertEqual(self.story.Text, prior)
        self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))

    def test_each_unit_uses_confirmed_native_enum(self):
        for unit, code in [('points', 1), ('percent_point_size', 2), ('percent_character_height', 0)]:
            with self.subTest(unit=unit):
                result = self.edit(line_spacing=24, paragraph_before=0, paragraph_after=8, spacing_unit=unit)
                self.assertEqual(self.calls[-1], (code, 24., 0., 8.))
                self.assertEqual(result['actual_spacing']['spacing_unit'], unit)

    def test_partial_unit_change_refused_before_write(self):
        self.error(ErrorCode.INVALID_ARGUMENT, line_spacing=14, spacing_unit='points')
        self.assertFalse(self.calls)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_paragraph_only_change_preserves_leading(self):
        result = self.edit(paragraph_before=0)
        self.assertEqual(self.calls, [(0, 100., 0., 6.)])
        self.assertEqual(result['actual_spacing']['line_spacing'], 100.)

    def test_invalid_values_are_preflight(self):
        for field in ('line_spacing', 'paragraph_before', 'paragraph_after'):
            for value in (True, '10', float('nan'), float('inf'), -1, 2001, 10**1000):
                with self.subTest(field=field, value_type=type(value).__name__):
                    self.error(ErrorCode.INVALID_ARGUMENT, **{field: value})
        self.error(ErrorCode.INVALID_ARGUMENT, line_spacing=0)
        self.error(ErrorCode.INVALID_ARGUMENT)
        self.error(ErrorCode.INVALID_ARGUMENT, line_spacing=10, spacing_unit='inches')
        self.assertFalse(self.calls)

    def test_nontext_refused(self):
        self.shape.Type = 1
        self.error(ErrorCode.INVALID_ARGUMENT, line_spacing=120)
        self.assertFalse(self.calls)

    def test_fitted_linked_and_unknown_scope_refused(self):
        for code, count in [(2, 1), (3, 1), (1, 2), (-1, 1), (0, 0)]:
            self.shape.Text.Type = code
            self.shape.Text.Frames = fixtures.Collection(*[object() for _ in range(count)])
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, line_spacing=120)
        self.assertFalse(self.calls)

    def test_mixed_unknown_negative_spacing_refused(self):
        for key, value in [('LineSpacingType', 3), ('LineSpacingType', 99), ('LineSpacing', None), ('LineSpacing', 0),
                           ('ParaSpacingBefore', -1), ('ParaSpacingAfter', float('nan'))]:
            old = getattr(self.story, key)
            self.story.__dict__[key] = value
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, line_spacing=120)
            self.story.__dict__[key] = old
        self.assertFalse(self.calls)

    def test_missing_native_method_is_preflight_and_redacted(self):
        del self.story.SetLineSpacing
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, line_spacing=120)
        self.assertFalse(self.calls)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_unreadable_horizontal_preservation_is_preflight(self):
        self.story.CharSpacing = None
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, line_spacing=120)
        self.assertFalse(self.calls)

    def test_preflight_change_preserves_concurrent_edit_without_native_call(self):
        def native_access(story):
            story.ParaSpacingAfter = 9.
            return story.__dict__['SetLineSpacing']
        with patch.object(fixtures.Story, 'SetLineSpacing', property(native_access), create=True):
            self.error(ErrorCode.INVALID_ARGUMENT, line_spacing=120)
        self.assertEqual(self.story.ParaSpacingAfter, 9.)
        self.assertFalse(self.calls)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_content_bound_is_preflight(self):
        self.story.Text = 'x' * 100001
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, line_spacing=120)
        self.assertFalse(self.calls)

    def test_native_failure_is_tracked_and_redacted(self):
        self.native_failure = True
        self.error(ErrorCode.COREL_COM_ERROR, line_spacing=120)
        self.assertTrue(self.bridge._operation_mutation_started)
        self.assertEqual(self.story.LineSpacing, 120.)

    def test_unexpected_content_style_horizontal_or_scope_changes_are_errors(self):
        changes = [(self.story, 'Text', 'Unexpected'), (self.story, 'Size', 24.),
                   (self.story, 'CharSpacing', 10.), (self.story, 'WordSpacing', 110.),
                   (self.shape.Text, 'Type', 2)]
        for target, key, value in changes:
            old = getattr(target, key)
            self.after_native = lambda target=target, key=key, value=value: setattr(target, key, value)
            self.error(ErrorCode.COREL_COM_ERROR, line_spacing=120)
            setattr(target, key, old)

    def test_spacing_mismatch_or_type_substitution_is_error(self):
        for key, value in [('LineSpacing', 99.), ('LineSpacingType', 1), ('ParaSpacingAfter', 8.)]:
            self.after_native = lambda key=key, value=value: setattr(self.story, key, value)
            self.error(ErrorCode.COREL_COM_ERROR, line_spacing=120)
            self.story.LineSpacingType, self.story.ParaSpacingAfter = 0, 6.

    def test_invalid_bounds_after_write_is_tracked(self):
        self.shape.SizeWidth = float('nan')
        self.error(ErrorCode.COREL_COM_ERROR, line_spacing=120)
        self.assertTrue(self.bridge._operation_mutation_started)

    def test_paragraph_overflow_is_native_and_not_fit_claim(self):
        self.shape.Text.Type, self.shape.Text.Overflow = 1, True
        result = self.edit(line_spacing=120)
        self.assertTrue(result['layout']['overflow'])
        self.assertEqual(result['layout']['overflow_scope'], 'linked_story')
        self.assertNotIn('fits', result)

    def test_signed_reference_survives_reorder_refuses_replacement(self):
        reference = self.bridge.get_text_properties(object_name='Title')['object']['object_reference']
        self.page.Shapes.items.insert(0, SimpleNamespace(Name='Other', StaticID=102, Type=1))
        self.edit(line_spacing=120, object_name='', object_reference=reference)
        replacement = copy.copy(self.shape)
        self.page.Shapes.items[1] = replacement
        self.shape.Layer.Shapes.items = [replacement]
        self.error(ErrorCode.OBJECT_NOT_FOUND, line_spacing=120, object_name='', object_reference=reference)
        self.assertEqual(len(self.calls), 1)

    def test_inactive_reference_page_refused(self):
        reference = self.bridge.get_text_properties(object_name='Title')['object']['object_reference']
        other = SimpleNamespace(Index=2, Shapes=fixtures.Collection(), AllLayers=fixtures.Collection())
        self.document.Pages.items.append(other)
        self.document.ActivePage = other
        self.error(ErrorCode.INVALID_ARGUMENT, line_spacing=120, object_name='', object_reference=reference)
        self.assertFalse(self.calls)

    def test_closed_document_refused_without_writes(self):
        self.bridge.app.Documents.items.clear()
        self.error(ErrorCode.NO_TARGET_DOCUMENT, line_spacing=120)
        self.assertFalse(self.calls)

    def test_late_native_failure_blocks_followup_worker_mutations(self):
        self.native_failure = True
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                result = server.set_text_spacing(line_spacing=120, object_name='Title')
                self.assertEqual(result['error']['code'], 'COREL_COM_ERROR')
                self.assertEqual(server.set_text_style(bold=True, object_name='Title')['error']['code'], 'RECOVERY_REQUIRED')
                self.assertTrue(server.get_text_properties(object_name='Title')['ok'])
        finally:
            dispatcher.close()

    def test_runtime_success_and_strict_request_schemas(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(t for t in registry['tools'] if t['name'] == 'set_text_spacing')
        result = success_result('set_text_spacing', self.edit(line_spacing=120), duration_ms=1)
        for name, value in [('output_schema', result), ('input_schema', {'line_spacing': 120, 'object_name': 'Title'})]:
            schema = dict(tool[name], schema_definitions=registry['schema_definitions'])
            Draft202012Validator(schema).validate(value)
        schema = dict(tool['input_schema'], schema_definitions=registry['schema_definitions'])
        for request in ({'line_spacing': None}, {'line_spacing': True}, {'line_spacing': 120, 'extra': 1}):
            with self.assertRaises(ValidationError):
                Draft202012Validator(schema).validate(request)

    def test_server_forwards_all_arguments(self):
        with patch.object(server, '_tool', return_value={}) as tool:
            server.set_text_spacing(24, 0, 8, 'points', 'Title', 0, None)
        tool.assert_called_once_with('set_text_spacing', 'set_text_spacing', 24, 0, 8, 'points', 'Title', 0, None)


if __name__ == '__main__':
    unittest.main()
