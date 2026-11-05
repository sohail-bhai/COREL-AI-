from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result
import powerclip_fakes as scene
from text_fitting_fakes import Paragraph, Text, prepare


class TextFittingTests(unittest.TestCase):
    def setUp(self):
        self.app, self.document, self.layer, _, _ = scene.fixture()
        prepare(self.app)
        self.source = Paragraph(self.layer, [scene.rectangle(1, 2, 3, .5)])
        self.bridge = CorelBridge()
        self.bridge.app = self.app
        self.bridge._bind_target_document(self.document)
        self.reference = self.bridge.get_text_properties(object_name='Body')['object']['object_reference']
        self.baseline = self.bridge._clip_baseline(self.document, self.layer)[0]

    def fit(self, **kwargs):
        return self.bridge.fit_paragraph_text(self.reference, **kwargs)

    def error(self, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            self.fit(**kwargs)
        self.assertNotIn('Private', str(caught.exception))
        self.assertNotIn('secret.cdr', str(caught.exception))
        return caught.exception

    def test_fits_independent_editable_copy_and_preserves_unicode_source(self):
        before = self.bridge._fitting_state(self.document, self.source)
        result = self.fit(result_name='ReadableBody')
        self.assertTrue(result['created'])
        self.assertTrue(result['source_preservation']['verified'])
        self.assertEqual(result['object']['object_name'], 'ReadableBody')
        self.assertFalse(result['overflow'])
        self.assertLessEqual(result['actual_size_points'], 12.)
        self.assertGreaterEqual(result['actual_size_points'], 11.9)
        self.assertLessEqual(result['probe_count'], 24)
        self.assertEqual(self.bridge._fitting_state(self.document, self.source), before)
        output = self.app.duplicates[-1]
        self.assertIsNot(output.Text.Story, self.source.Text.Story)
        self.assertEqual(output.Text.Story.Text, self.source.Text.Story.Text)
        self.assertEqual(output.Type, 6)
        self.assertEqual((self.document.Unit, self.document.ReferencePoint), (3, 9))

    def test_already_fitting_copy_does_not_enlarge_or_rewrite_text(self):
        self.app.fitting_threshold = 100
        result = self.fit()
        self.assertEqual(result['actual_size_points'], 18.)
        self.assertEqual(result['probe_count'], 0)
        self.assertFalse(self.app.size_probes)

    def test_minimum_overflow_removes_owned_copy_and_reports_reason(self):
        self.app.fitting_threshold = 7
        error = self.error()
        self.assertEqual(error.code, ErrorCode.INVALID_ARGUMENT)
        self.assertIn('minimum readable size', error.details['fitting_failure'])
        self.assertTrue(error.details['rollback']['verified'])
        self.assertTrue(error.details['rollback']['output_removed'])
        self.assertEqual(self.bridge._clip_baseline(self.document, self.layer)[0], self.baseline)
        self.assertEqual(self.source.Text.Story.Size, 18.)

    def test_native_single_rounding_does_not_cross_readability_minimum(self):
        self.app.fitting_threshold = 8.3001
        result = self.fit(minimum_size_points=8.3, size_tolerance_points=.01)
        self.assertGreaterEqual(result['actual_size_points'], 8.3)
        self.assertTrue(all(p['actual_size_points'] >= 8.3 for p in result['probes']))

    def test_widest_range_and_smallest_tolerance_stay_within_probe_limit(self):
        self.source.Text.Story.__dict__['Size'] = 500.
        self.app.fitting_threshold = 250.25
        result = self.fit(minimum_size_points=1, size_tolerance_points=.01)
        self.assertLessEqual(result['probe_count'], 24)
        self.assertLessEqual(result['actual_size_points'], 250.25)
        self.assertGreaterEqual(result['actual_size_points'], 250.24)

    def test_invalid_parameters_fail_before_copy(self):
        for kwargs in ({'minimum_size_points': True}, {'minimum_size_points': 0}, {'minimum_size_points': 19},
                       {'minimum_size_points': float('nan')}, {'size_tolerance_points': .001},
                       {'size_tolerance_points': float('inf')}, {'result_name': 'bad\nname'}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.error(**kwargs).code, ErrorCode.INVALID_ARGUMENT)
        self.assertFalse(self.app.duplicates)

    def test_linked_fitted_artistic_and_unknown_overflow_are_preflight(self):
        for key, value in [('frame_count', 2), ('unknown_overflow', True)]:
            old = getattr(self.app, key)
            setattr(self.app, key, value)
            self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
            setattr(self.app, key, old)
        self.source.Text.Type = 0
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.source.Text.Type = 1
        for key in ('container', 'fitted'):
            setattr(self.source.Text, key, True)
            self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
            setattr(self.source.Text, key, False)
        self.assertFalse(self.app.duplicates)

    def test_mixed_style_spacing_long_text_and_effects_are_preflight(self):
        self.source.Text.Story.Font = ''
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.source.Text.Story.Font = 'Arial'
        self.source.Text.Story.LineSpacingType = 3
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.source.Text.Story.LineSpacingType = 0
        self.source.Text.Story.Text = 'x' * 10001
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.source.Text.Story.Text = 'Body'
        self.source.Effects.items.append(object())
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertFalse(self.app.duplicates)

    def test_closed_document_does_not_fallback(self):
        self.app.Documents.items.clear()
        self.assertEqual(self.error().code, ErrorCode.NO_TARGET_DOCUMENT)
        self.assertFalse(self.app.duplicates)

    def test_replaced_source_refused_before_copy(self):
        replacement = copy.copy(self.source)
        self.layer.Shapes.items[-1] = replacement
        self.document.ActivePage.Shapes.items[-1] = replacement
        self.assertEqual(self.error().code, ErrorCode.OBJECT_NOT_FOUND)
        self.assertFalse(self.app.duplicates)

    def test_source_preflight_change_refused_without_creating_output(self):
        original = self.bridge._fitting_state
        reads = []
        def observe(document, shape):
            if shape is self.source:
                reads.append(1)
                if len(reads) == 2:
                    self.source.Text.Story.Text = 'Concurrent preflight edit'
            return original(document, shape)
        with patch.object(self.bridge, '_fitting_state', side_effect=observe):
            self.assertEqual(self.error().code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.source.Text.Story.Text, 'Concurrent preflight edit')
        self.assertFalse(self.app.duplicates)

    def test_unsupported_appearance_is_refused_before_copy(self):
        self.source.Fill.Type = 2
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertFalse(self.app.duplicates)

    def test_unreadable_frame_background_is_not_inferred_to_be_empty(self):
        original = Text.Frame.fget
        def frame(text):
            value = original(text)
            del value.Fill
            return value
        with patch.object(Text, 'Frame', property(frame)):
            self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertFalse(self.app.duplicates)

    def test_column_geometry_is_preserved_and_changed_gutters_are_detected(self):
        self.app.column_count = 2
        result = self.fit()
        self.assertTrue(result['source_preservation']['verified'])
        self.app.on_size = lambda story: setattr(self.app, 'column_gutter', .75)
        self.source.Text.Story.__dict__['Size'] = 18.
        error = self.error()
        self.assertFalse(error.details['rollback']['verified'])
        self.assertEqual(self.app.column_gutter, .75)

    def test_unreadable_column_width_is_preflight(self):
        self.app.column_width = None
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.app.column_width, self.app.column_count, self.app.column_gutter = 3., 2, None
        self.assertEqual(self.error().code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertFalse(self.app.duplicates)

    def test_reused_duplicate_does_not_touch_or_delete_source(self):
        self.app.reuse_duplicate = True
        error = self.error()
        self.assertTrue(error.details['ownership_uncertain'])
        self.assertEqual(self.source.Text.Story.Size, 18.)
        self.assertEqual(self.bridge._clip_baseline(self.document, self.layer)[0], self.baseline)

    def test_shared_story_is_never_written_or_deleted(self):
        self.app.share_story = True
        error = self.error()
        self.assertTrue(error.details['rollback']['output_retained'])
        self.assertFalse(self.app.size_probes)
        self.assertEqual(self.source.Text.Story.Size, 18.)

    def test_verified_cleanup_allows_followup_worker_mutations(self):
        self.app.fail_size = True
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                result = server.fit_paragraph_text(self.reference)
                self.assertEqual(result['error']['code'], 'COREL_COM_ERROR')
                self.assertTrue(result['error']['details']['rollback']['verified'])
                self.app.fail_size = False
                self.assertTrue(server.set_text_style(bold=True, object_reference=self.reference)['ok'])
                self.assertTrue(server.get_text_properties(object_reference=self.reference)['ok'])
        finally:
            dispatcher.close()

    def test_unverified_cleanup_quarantines_followup_worker_mutations(self):
        self.app.on_size = lambda story: story.__dict__.update(Text='Concurrent output edit')
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                result = server.fit_paragraph_text(self.reference)
                self.assertFalse(result['error']['details']['rollback']['verified'])
                self.assertEqual(server.set_text_style(bold=True, object_reference=self.reference)['error']['code'], 'RECOVERY_REQUIRED')
                self.assertTrue(server.get_text_properties(object_reference=self.reference)['ok'])
        finally:
            dispatcher.close()

    def test_changed_source_is_preserved_and_never_restored_from_stale_snapshot(self):
        self.app.on_size = lambda story: self.source.Text.Story.__dict__.update(Text='Concurrent source edit')
        error = self.error()
        self.assertEqual(self.source.Text.Story.Text, 'Concurrent source edit')
        self.assertFalse(error.details['rollback']['verified'])

    def test_changed_output_content_is_retained_for_inspection(self):
        self.app.on_size = lambda story: story.__dict__.update(Text='Concurrent output edit')
        error = self.error()
        self.assertTrue(error.details['rollback']['output_retained'])
        self.assertEqual(self.app.duplicates[-1].Text.Story.Text, 'Concurrent output edit')
        self.assertNotEqual(self.source.Text.Story.Text, 'Concurrent output edit')

    def test_failed_output_deletion_is_explicit_and_source_unchanged(self):
        self.app.fail_size, self.app.fail_delete = True, True
        error = self.error()
        self.assertFalse(error.details['rollback']['verified'])
        self.assertTrue(error.details['rollback']['output_retained'])
        self.assertEqual(error.details['rollback']['error_type'], 'RuntimeError')
        self.assertEqual(self.source.Text.Story.Size, 18.)

    def test_native_end_failure_is_not_retried_or_called_on_an_unknown_group(self):
        original = self.document.EndCommandGroup
        calls = []
        def end():
            calls.append(1)
            original()
            raise RuntimeError('Private command-group failure')
        self.document.EndCommandGroup = end
        error = self.error()
        self.assertEqual(len(calls), 1)
        self.assertTrue(error.details['rollback']['command_group_uncertain'])

    def test_late_output_edit_is_retained_after_command_group_closes(self):
        original = self.document.EndCommandGroup
        def end():
            original()
            self.app.duplicates[-1].Text.Story.Text = 'Late concurrent edit'
        self.document.EndCommandGroup = end
        error = self.error()
        self.assertTrue(error.details['rollback']['output_retained'])
        self.assertEqual(self.app.duplicates[-1].Text.Story.Text, 'Late concurrent edit')

    def test_unaccounted_late_shape_is_not_deleted_or_reported_as_clean(self):
        original = self.document.EndCommandGroup
        def end():
            original()
            scene.Shape(self.layer, [scene.rectangle(10, 10, 1, 1)], 'Concurrent artwork', 3)
        self.document.EndCommandGroup = end
        error = self.error()
        self.assertFalse(error.details['rollback']['verified'])
        self.assertTrue(any(s.Name == 'Concurrent artwork' for s in self.layer.Shapes.items))
        self.assertEqual(self.source.Text.Story.Size, 18.)

    def test_copy_moved_to_another_layer_is_retained_and_recovery_is_required(self):
        other = scene.BaseLayer(self.document.ActivePage, 'Elsewhere')
        self.document.ActivePage.AllLayers.items.append(other)
        original = self.document.EndCommandGroup
        def end():
            original()
            output = self.app.duplicates[-1]
            self.layer.Shapes.items.remove(output)
            output.Layer = other
            other.Shapes.items.append(output)
        self.document.EndCommandGroup = end
        error = self.error()
        self.assertFalse(error.details['rollback']['verified'])
        self.assertTrue(error.details['rollback']['output_retained'])
        self.assertEqual(other.Shapes.Count, 1)

    def test_runtime_success_and_request_schemas(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(t for t in registry['tools'] if t['name'] == 'fit_paragraph_text')
        schema = dict(tool['output_schema'], schema_definitions=registry['schema_definitions'])
        Draft202012Validator(schema).validate(success_result('fit_paragraph_text', self.fit(), duration_ms=1))
        schema = dict(tool['input_schema'], schema_definitions=registry['schema_definitions'])
        Draft202012Validator(schema).validate({'object_reference': self.reference})
        for request in ({}, {'object_reference': self.reference, 'minimum_size_points': True},
                        {'object_reference': self.reference, 'extra': 1}):
            with self.assertRaises(ValidationError):
                Draft202012Validator(schema).validate(request)

    def test_server_forwards_arguments(self):
        with patch.object(server, '_tool', return_value={}) as tool:
            server.fit_paragraph_text(self.reference, 10, .2, 'Fitted')
        tool.assert_called_once_with('fit_paragraph_text', 'fit_paragraph_text', self.reference, 10, .2, 'Fitted')


if __name__ == '__main__':
    unittest.main()
