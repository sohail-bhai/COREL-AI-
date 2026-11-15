from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from dispatcher_fakes import exclusive_dispatcher
from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.horizontal_spacing import FIELDS, SCALARS
from corel_operator.results import success_result
import test_typography as fixtures


class HorizontalSpacingTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.TypographyTests()
        fixture.setUp()
        self.bridge, self.story, self.shape = fixture.bridge, fixture.story, fixture.shape
        self.document, self.page = fixture.document, fixture.page
        self.story.ParaSpacingBefore, self.story.ParaSpacingAfter = 4., 6.
        self.frame = SimpleNamespace(IsInsideContainer=False, IsFittedToPath=False, FrameShape=self.shape,
            ColumnCount=1, VerticalAlignment=0, ColumnWidth=lambda index: 3., ColumnGutter=lambda index: .1)
        self.shape.Text.Frame = self.frame
        self.limits = SimpleNamespace(MaxCharacterSpacing=2000., MinWordSpacing=0., MaxWordSpacing=2000.)
        self.get_calls, self.set_calls, self.created = [], [], []
        self.after_create = lambda: None
        self.after_native = lambda: None
        self.native_failure = False

        def getter(frames):
            self.get_calls.append(frames)
            return SimpleNamespace(**{attr: getattr(self.story, SCALARS[key]) for key, attr in FIELDS.items()})

        def setter(frames, pending):
            self.set_calls.append((frames, copy.copy(pending)))
            for key, attr in FIELDS.items():
                self.story.__dict__[SCALARS[key]] = getattr(pending, attr)
            self.after_native()
            if self.native_failure:
                raise RuntimeError('Private text C:/client/artwork.cdr')

        def creator():
            pending = SimpleNamespace()
            self.created.append(pending)
            self.after_create()
            return pending

        self.shape.Text.GetSpaceProperties = getter
        self.shape.Text.SetSpaceProperties = setter
        self.shape.Text.GetAlignProperties = lambda frames: self.limits
        self.bridge.app.CreateStructSpaceProperties = creator

    def edit(self, **kwargs):
        kwargs.setdefault('object_name', 'Title')
        return self.bridge.set_text_horizontal_spacing(**kwargs)

    def error(self, code, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            self.edit(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn('Private', str(caught.exception))
        self.assertNotIn('artwork.cdr', str(caught.exception))

    def test_character_only_preserves_word_and_leading(self):
        content = self.story.Text
        result = self.edit(character_spacing_percent=-10)
        self.assertEqual(result['actual_spacing']['character_spacing_percent'], -10.)
        self.assertEqual(result['actual_spacing']['word_spacing_percent'], 100.)
        self.assertEqual(result['spacing_unit'], 'percent_space_character')
        self.assertEqual(result['requested_spacing'], {'character_spacing_percent': -10.})
        self.assertEqual(self.story.Text, content)
        self.assertTrue(result['content_preserved'])
        self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))
        self.assertEqual(self.set_calls[0][0], 2)
        self.assertTrue(all(frames == 2 for frames in self.get_calls))
        self.assertEqual(set(vars(self.set_calls[0][1])), set(FIELDS.values()))
        for key in ('line_spacing', 'paragraph_before', 'paragraph_after', 'spacing_type_code'):
            self.assertEqual(result['before_spacing'][key], result['actual_spacing'][key])

    def test_word_only_preserves_character_and_point_leading(self):
        self.story.LineSpacingType, self.story.LineSpacing = 1, 18.
        result = self.edit(word_spacing_percent=125)
        self.assertEqual(result['actual_spacing']['word_spacing_percent'], 125.)
        self.assertEqual(result['actual_spacing']['character_spacing_percent'], 0.)
        self.assertEqual(self.story.LineSpacingType, 1)
        self.assertEqual(self.story.LineSpacing, 18.)

    def test_both_endpoints_are_representable(self):
        for char, word in ((-100, 0), (2000, 2000)):
            result = self.edit(character_spacing_percent=char, word_spacing_percent=word)
            self.assertEqual(result['actual_spacing']['character_spacing_percent'], char)
            self.assertEqual(result['actual_spacing']['word_spacing_percent'], word)

    def test_invalid_values_refused_before_structure_creation(self):
        for field in ('character_spacing_percent', 'word_spacing_percent'):
            for value in (True, '10', float('nan'), float('inf'), -101, 2001, 10**1000):
                self.error(ErrorCode.INVALID_ARGUMENT, **{field: value})
        self.error(ErrorCode.INVALID_ARGUMENT, word_spacing_percent=-1)
        self.error(ErrorCode.INVALID_ARGUMENT)
        self.assertFalse(self.created)
        self.assertFalse(self.set_calls)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_existing_justification_limits_are_enforced_without_overrides(self):
        self.limits.MaxCharacterSpacing = 20.
        self.limits.MinWordSpacing, self.limits.MaxWordSpacing = 80., 120.
        for kwargs in ({'character_spacing_percent': 21}, {'word_spacing_percent': 79}, {'word_spacing_percent': 121}):
            self.error(ErrorCode.INVALID_ARGUMENT, **kwargs)
        self.assertFalse(self.created)
        self.assertEqual(self.limits.MaxCharacterSpacing, 20.)

    def test_mixed_or_unreadable_limits_are_refused(self):
        for attr, value in (('MaxCharacterSpacing', None), ('MinWordSpacing', float('nan')), ('MinWordSpacing', 2001)):
            old = getattr(self.limits, attr)
            setattr(self.limits, attr, value)
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
            setattr(self.limits, attr, old)
        self.assertFalse(self.set_calls)

    def test_linked_fitted_or_unknown_scope_refused(self):
        for code in (2, 3, 99):
            self.shape.Text.Type = code
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
        self.shape.Text.Type = 1
        self.shape.Text.Frames.items.append(object())
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
        self.assertFalse(self.created)

    def test_missing_structure_interface_does_not_fall_back_to_scalar_writes(self):
        for owner, name in ((self.shape.Text, 'GetSpaceProperties'), (self.shape.Text, 'SetSpaceProperties'),
                            (self.shape.Text, 'GetAlignProperties'), (self.bridge.app, 'CreateStructSpaceProperties')):
            old = getattr(owner, name)
            setattr(owner, name, None)
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
            setattr(owner, name, old)
        self.assertEqual(self.story.CharSpacing, 0.)
        self.assertFalse(self.set_calls)

    def test_mixed_spacing_or_basic_style_refused(self):
        for key, value in (('LineSpacingType', 3), ('CharSpacing', None), ('WordSpacing', -1), ('Size', None)):
            old = getattr(self.story, key)
            setattr(self.story, key, value)
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
            setattr(self.story, key, old)
        self.assertFalse(self.set_calls)

    def test_scalar_structure_disagreement_refused_before_write(self):
        getter = self.shape.Text.GetSpaceProperties
        def wrong_basis(frames):
            result = getter(frames)
            result.CharacterSpacing = 100.
            return result
        self.shape.Text.GetSpaceProperties = wrong_basis
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
        self.assertFalse(self.created)

    def test_bound_getter_structure_is_never_populated(self):
        original = self.shape.Text.GetSpaceProperties(2)
        self.shape.Text.GetSpaceProperties = lambda frames: original
        self.bridge.app.CreateStructSpaceProperties = lambda: original
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
        self.assertEqual(original.CharacterSpacing, 0.)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_concurrent_content_edit_before_application_is_preserved(self):
        self.after_create = lambda: setattr(self.story, 'Text', 'Concurrent user edit')
        self.error(ErrorCode.INVALID_ARGUMENT, character_spacing_percent=10)
        self.assertEqual(self.story.Text, 'Concurrent user edit')
        self.assertFalse(self.set_calls)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_concurrent_style_limits_and_bounds_changes_refused(self):
        for owner, attr, value in ((self.story, 'Bold', True), (self.limits, 'MaxWordSpacing', 120.),
                                   (self.shape, 'SizeWidth', 4.), (self.story, 'ParaSpacingBefore', 9.)):
            self.setUp()
            # Select owners from the newly created fixture.
            owner = self.story if attr in ('Bold', 'ParaSpacingBefore') else self.limits if attr == 'MaxWordSpacing' else self.shape
            self.after_create = lambda owner=owner, attr=attr, value=value: setattr(owner, attr, value)
            self.error(ErrorCode.INVALID_ARGUMENT, character_spacing_percent=10)
            self.assertEqual(getattr(owner, attr), value)
            self.assertFalse(self.set_calls)

    def test_native_failure_is_tracked_without_replay(self):
        self.native_failure = True
        self.error(ErrorCode.COREL_COM_ERROR, character_spacing_percent=10)
        self.assertTrue(self.bridge._operation_mutation_started)
        self.assertEqual(self.story.CharSpacing, 10.)
        self.assertEqual(len(self.set_calls), 1)

    def test_native_spacing_substitution_is_not_success(self):
        self.after_native = lambda: setattr(self.story, 'CharSpacing', 8.)
        self.error(ErrorCode.COREL_COM_ERROR, character_spacing_percent=10)
        self.assertEqual(self.story.CharSpacing, 8.)
        self.assertTrue(self.bridge._operation_mutation_started)

    def test_unrequested_native_changes_require_reconciliation(self):
        for attr, value in (('Text', 'Changed'), ('Size', 24.), ('LineSpacing', 99.),
                            ('LineSpacingType', 1), ('ParaSpacingAfter', 9.)):
            self.setUp()
            self.after_native = lambda attr=attr, value=value: setattr(self.story, attr, value)
            self.error(ErrorCode.COREL_COM_ERROR, character_spacing_percent=10)
            self.assertEqual(getattr(self.story, attr), value)
            self.assertEqual(len(self.set_calls), 1)

    def test_native_limit_and_scope_changes_are_errors(self):
        self.after_native = lambda: setattr(self.limits, 'MaxCharacterSpacing', 20.)
        self.error(ErrorCode.COREL_COM_ERROR, character_spacing_percent=10)
        self.setUp()
        self.after_native = lambda: self.shape.Text.Frames.items.append(object())
        self.error(ErrorCode.COREL_COM_ERROR, character_spacing_percent=10)

    def test_native_paragraph_frame_change_is_preserved_for_inspection(self):
        self.shape.Text.Type = 1
        self.after_native = lambda: setattr(self.shape, 'SizeWidth', 3.001)
        self.error(ErrorCode.COREL_COM_ERROR, word_spacing_percent=110)
        self.assertEqual(self.shape.SizeWidth, 3.001)

    def test_container_path_or_ambiguous_paragraph_frame_is_refused(self):
        self.shape.Text.Type = 1
        for attr, value in (('IsInsideContainer', True), ('IsFittedToPath', True),
                            ('FrameShape', object()), ('ColumnCount', 21)):
            old = getattr(self.frame, attr)
            setattr(self.frame, attr, value)
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, word_spacing_percent=110)
            setattr(self.frame, attr, old)
        self.assertFalse(self.set_calls)

    def test_multicolumn_geometry_is_preserved_and_native_changes_detected(self):
        self.shape.Text.Type = 1
        self.frame.ColumnCount = 2
        result = self.edit(word_spacing_percent=110)
        self.assertTrue(result['content_preserved'])
        self.after_native = lambda: setattr(self.frame, 'ColumnGutter', lambda index: .2)
        self.error(ErrorCode.COREL_COM_ERROR, word_spacing_percent=115)
        self.assertEqual(self.frame.ColumnGutter(1), .2)

    def test_paragraph_overflow_is_reported_without_fit_claim(self):
        self.shape.Text.Type, self.shape.Text.Overflow = 1, True
        result = self.edit(word_spacing_percent=110)
        self.assertTrue(result['layout']['overflow'])
        self.assertEqual(result['layout']['overflow_scope'], 'linked_story')
        self.assertNotIn('fits', result)

    def test_late_change_during_measured_bounds_is_preserved_and_reported(self):
        measure = self.bridge._typography_bounds
        def late_edit(document, shape):
            bounds = measure(document, shape)
            self.story.Text = 'Late concurrent edit'
            return bounds
        with patch.object(self.bridge, '_typography_bounds', side_effect=late_edit):
            self.error(ErrorCode.COREL_COM_ERROR, character_spacing_percent=10)
        self.assertEqual(self.story.Text, 'Late concurrent edit')
        self.assertEqual(len(self.set_calls), 1)

    def test_content_and_geometry_bounds_refused_before_native_setters(self):
        for content in ('', 'x' * 100001):
            self.story.Text = content
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
        self.story.Text = 'Valid text'
        self.shape.SizeWidth = float('nan')
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
        self.assertFalse(self.set_calls)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_stale_target_replacement_after_preflight_is_refused(self):
        replacement = copy.copy(self.shape)
        def replace():
            self.page.Shapes.items[:] = [replacement]
            self.shape.Layer.Shapes.items[:] = [replacement]
        self.after_create = replace
        self.error(ErrorCode.OBJECT_NOT_FOUND, character_spacing_percent=10)
        self.assertFalse(self.set_calls)

    def test_default_pause_and_background_mode_require_exclusive_window(self):
        self.bridge.configure_editing_mode('paused')
        self.error(ErrorCode.CONFIRMATION_REQUIRED, character_spacing_percent=10)
        foreground = SimpleNamespace(Name='Foreground.cdr')
        self.bridge.app.Documents.items.append(foreground)
        self.bridge.app.ActiveDocument = foreground
        self.bridge.configure_editing_mode('background_document')
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, character_spacing_percent=10)
        self.assertFalse(self.set_calls)

    def test_pause_after_structure_preparation_stops_native_boundary(self):
        self.after_create = lambda: self.bridge.configure_editing_mode('paused')
        self.error(ErrorCode.CONFIRMATION_REQUIRED, character_spacing_percent=10)
        self.assertFalse(self.set_calls)
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_worker_quarantines_failure_and_allows_inspection(self):
        self.native_failure = True
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = exclusive_dispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                result = server.set_text_horizontal_spacing(character_spacing_percent=10, object_name='Title')
                self.assertEqual(result['error']['code'], 'COREL_COM_ERROR')
                self.assertEqual(server.set_text_style(bold=True, object_name='Title')['error']['code'], 'RECOVERY_REQUIRED')
                self.assertTrue(server.get_text_properties(object_name='Title')['ok'])
        finally:
            dispatcher.close()

    def test_runtime_and_strict_schema_parity(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text())
        tool = next(t for t in registry['tools'] if t['name'] == 'set_text_horizontal_spacing')
        request = {'character_spacing_percent': -100, 'word_spacing_percent': 0, 'object_name': 'Title'}
        result = success_result(tool['name'], self.edit(**request), duration_ms=1)
        for key, value in (('input_schema', request), ('output_schema', result)):
            Draft202012Validator(dict(tool[key], schema_definitions=registry['schema_definitions'])).validate(value)
        validator = Draft202012Validator(dict(tool['input_schema'], schema_definitions=registry['schema_definitions']))
        for bad in ({'word_spacing_percent': None}, {'word_spacing_percent': True},
                    {'word_spacing_percent': -1}, {'character_spacing_percent': 10, 'extra': 1}):
            with self.assertRaises(ValidationError):
                validator.validate(bad)

    def test_server_forwards_all_arguments(self):
        with patch.object(server, '_tool', return_value={}) as tool:
            server.set_text_horizontal_spacing(10, 110, 'Title', 0, None)
        tool.assert_called_once_with('set_text_horizontal_spacing', 'set_text_horizontal_spacing', 10, 110, 'Title', 0, None)


if __name__ == '__main__':
    unittest.main()
