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
from contour_offset_fakes import fixture, Group, Shape
from test_layout import Collection
from test_process_colors import cmyk, rgb, native_color
from vector_fakes import Curve, rectangle
import gradient_fakes
from test_gradients import stops


class ContourOffsetTests(unittest.TestCase):
    def setUp(self):
        self.app, self.document, self.layer, self.source = fixture()
        self.bridge = CorelBridge(); self.bridge.app = self.app; self.bridge._bind_target_document(self.document)
        self.reference = self.bridge.get_object_info(object_name=self.source.Name)['object']['object_reference']
        self.baseline = list(self.layer.Shapes.items)

    def apply(self, distance=.1, **kwargs):
        return self.bridge.create_contour_offsets(self.reference, distance, **kwargs)

    def error(self, call, *args, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            call(*args, **kwargs)
        return caught.exception

    def test_outside_multistep_bounds_color_and_source_preservation(self):
        source = self.bridge._offset_source_signature(self.document, self.source)
        result = self.apply(steps=3, color=cmyk(), result_name_prefix='Border')
        self.assertEqual(result['created_count'], 3)
        self.assertEqual(result['requested_steps'], 3)
        for step, item in enumerate(result['objects'], 1):
            bounds = item['curve']['bounds_inches']
            self.assertAlmostEqual(bounds['x'], 1 - .1 * step)
            self.assertAlmostEqual(bounds['y'], 1 - .1 * step)
            self.assertAlmostEqual(bounds['width'], 3 + .2 * step)
            self.assertAlmostEqual(bounds['height'], 2 + .2 * step)
            self.assertEqual(item['object']['object_name'], f'Border_{step:03d}')
            self.assertIsNotNone(item['object']['object_reference'])
            shape, _ = self.bridge._resolve_object_reference(self.document, item['object']['object_reference'])
            self.assertEqual(shape.Fill.Type, 1); self.assertEqual(shape.Outline.Type, 0)
            self.assertEqual(shape.Transparency.Type, 0); self.assertEqual(shape.Effects.Count, 0)
            self.assertEqual(self.bridge._fill_readback(shape)['color']['value'], {k: v for k, v in cmyk().items() if k != 'model'})
        self.assertEqual(self.bridge._offset_source_signature(self.document, self.source), source)
        self.assertEqual([s for s in self.layer.Shapes.items if s in self.baseline], self.baseline)
        self.assertEqual(self.document.Unit, 3); self.assertEqual(self.document.ReferencePoint, 9)
        self.assertTrue(result['source_preservation']['verified'])

    def test_inside_contours_shrink_and_empty_collapsed_result_is_explicit(self):
        result = self.apply(direction='inside', steps=2)
        self.assertEqual(result['created_count'], 2)
        self.assertAlmostEqual(result['objects'][0]['curve']['bounds_inches']['width'], 2.8)
        self.setUp()
        empty = self.apply(2., direction='inside', steps=3)
        self.assertFalse(empty['created']); self.assertTrue(empty['empty_result'])
        self.assertEqual(empty['objects'], []); self.assertEqual(self.layer.Shapes.items, self.baseline)

    def test_partially_collapsed_steps_report_actual_curves_without_fabricated_step_map(self):
        result = self.apply(.6, direction='inside', steps=5)
        self.assertEqual(result['requested_steps'], 5); self.assertEqual(result['created_count'], 1)
        self.assertEqual(result['native_parameters']['Steps'], 5)

    def test_compound_generated_paths_remain_complete_editable_curves(self):
        self.app.flags['compound_output'] = True
        result = self.apply(steps=3)
        self.assertEqual(result['created_count'], 1)
        self.assertEqual(len(result['objects'][0]['curve']['paths']), 3)
        self.assertEqual(result['objects'][0]['curve']['node_count'], 12)

    def test_nested_generated_groups_are_flattened_with_preserved_child_identities(self):
        self.app.flags['nested_group'] = True
        result = self.apply(steps=2)
        self.assertEqual(result['created_count'], 2)
        self.assertTrue(all(s.Type == 3 for s in self.layer.Shapes.items if s not in self.baseline))

    def test_separation_can_replace_only_containers_while_retaining_proven_leaves(self):
        self.app.flags['replace_container'] = True
        self.assertEqual(self.apply(steps=2)['created_count'], 2)

    def test_primitives_convert_only_the_owned_copy(self):
        self.source.Type = 1
        self.reference = self.bridge.get_object_info(object_name=self.source.Name)['object']['object_reference']
        result = self.apply()
        self.assertEqual(self.source.Type, 1)
        self.assertEqual(result['created_count'], 1)

    def test_all_native_corner_controls_and_limit_read_back(self):
        for kind in self.bridge.adapter.CONTOUR_CORNER_CODES:
            self.setUp()
            result = self.apply(corner_type=kind, miter_limit=4.)
            self.assertEqual(result['native_parameters']['CornerType'], self.bridge.adapter.CONTOUR_CORNER_CODES[kind])
            self.assertEqual(result['native_parameters']['MiterLimit'], 4.)
            self.assertEqual(result['native_parameters']['EndCapType'], 0)

    def test_small_offsets_cannot_pass_with_unchanged_geometry(self):
        self.app.flags['wrong_extent'] = True
        failure = self.error(self.apply, .0001)
        self.assertEqual(failure.code, ErrorCode.COREL_COM_ERROR)
        self.assertTrue(failure.details['rollback']['verified'])

    def test_effect_bounding_box_changes_do_not_change_controller_curve_contract(self):
        self.app.flags['controller_effect_bounds'] = True
        self.assertTrue(self.apply()['source_preservation']['verified'])

    def test_controller_path_or_copied_node_type_changes_are_detected(self):
        for flag in ('controller_corruption', 'duplicate_node_type'):
            self.setUp(); self.app.flags[flag] = True
            self.assertTrue(self.error(self.apply).details['rollback']['verified'])

    def test_invalid_parameters_fail_before_duplication(self):
        for distance in (True, 0, -1, 101., float('nan'), float('inf')):
            self.assertEqual(self.error(self.apply, distance).code, ErrorCode.INVALID_ARGUMENT)
        for kwargs in ({'direction': 'center'}, {'direction': True}, {'steps': 0}, {'steps': True}, {'steps': 33},
                       {'corner_type': 'unlimited'}, {'miter_limit': -1}, {'miter_limit': float('nan')},
                       {'result_name_prefix': ''}, {'result_name_prefix': 'x' * 111}, {'result_name_prefix': 'bad\nname'},
                       {'color': cmyk(k=101)}):
            self.assertEqual(self.error(self.apply, **kwargs).code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates, [])

    def test_open_paths_and_existing_effects_fail_before_mutation(self):
        path = rectangle(1, 1, 3, 2); path['closed'] = False; path['segments'] = path['segments'][:-1]
        self.source.curve = Curve.from_paths(self.app, [path])
        self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.setUp(); self.source.Effects.items = [SimpleNamespace(Type=6)]
        self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.app.duplicates, [])

    def test_complete_source_cubic_handles_are_preserved(self):
        path = {'start': {'x': 1., 'y': 1.}, 'closed': True, 'segments': [
            {'type': 'cubic', 'control1': {'x': 1., 'y': 4.}, 'control2': {'x': 4., 'y': 4.}, 'end': {'x': 4., 'y': 1.}},
            {'type': 'line', 'end': {'x': 1., 'y': 1.}}]}
        self.source.curve = Curve.from_paths(self.app, [path])
        before = self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
        result = self.apply()
        self.assertTrue(result['source_preservation']['verified'])
        self.assertEqual(self.bridge.get_curve_geometry(object_reference=self.reference)['curve'], before)

    def test_compound_source_paths_are_preserved_without_assuming_output_winding(self):
        self.source.curve = Curve.from_paths(self.app, [rectangle(1, 1, 3, 2), rectangle(2, 1.5, .5, .5)])
        before = self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
        self.assertTrue(self.apply()['source_preservation']['verified'])
        self.assertEqual(self.bridge.get_curve_geometry(object_reference=self.reference)['curve'], before)

    def test_complete_process_gradient_and_uniform_transparency_sources_are_preserved(self):
        self.source.Fill = gradient_fakes.Fill(self.source)
        self.bridge.set_gradient_fill(stops(middle=True), object_reference=self.reference)
        self.source.Transparency.Type = 1; self.source.Transparency.Uniform = 40
        before = self.bridge._offset_source_signature(self.document, self.source)
        self.assertTrue(self.apply()['source_preservation']['verified'])
        self.assertEqual(self.bridge._offset_source_signature(self.document, self.source), before)

    def test_baseline_clip_descendants_are_included_in_foreign_curve_alias_checks(self):
        child = Shape(self.layer, Curve.from_paths(self.app, [rectangle(12, 12)]), 'ClippedBaselineChild')
        self.layer.Shapes.items.remove(child); self.document.ActivePage.Shapes.items.remove(child)
        self.app.other_source.PowerClip = SimpleNamespace(Parent=self.app.other_source, Shapes=Collection(child))
        self.app.flags['shared_foreign_curve'] = True
        self.app.other_source.curve = child.curve
        failure = self.error(self.apply)
        self.assertTrue(failure.details['ownership_uncertain'])
        self.assertNotIn(child.StaticID, self.app.deleted)

    def test_unreadable_clip_effect_or_color_metadata_is_refused(self):
        for kind in ('clip', 'effects', 'fill', 'outline', 'transparency'):
            self.setUp()
            if kind == 'clip': del self.source.PowerClip
            elif kind == 'effects': del self.source.Effects
            elif kind == 'fill': self.source.Fill.Type = 9
            elif kind == 'outline': del self.source.Outline.Color.RGBGreen
            else: self.source.Transparency.Type = 2
            self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
            self.assertEqual(self.app.duplicates, [])

    def test_native_color_factory_mismatch_fails_before_mutation(self):
        self.app.CreateCMYKColor = lambda *args: native_color(rgb())
        self.assertEqual(self.error(self.apply, color=cmyk()).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.app.duplicates, [])

    def test_duplicate_aliases_and_foreign_mutable_curves_never_delete_originals(self):
        for flag in ('reuse_duplicate', 'shared_source_curve', 'shared_foreign_curve'):
            self.setUp(); self.app.flags[flag] = True
            failure = self.error(self.apply)
            self.assertTrue(failure.details['ownership_uncertain'])
            self.assertNotIn(self.source.StaticID, self.app.deleted)
            self.assertNotIn(self.app.other_source.StaticID, self.app.deleted)

    def test_primitive_copy_may_not_become_original_display_curve_data(self):
        self.source.Type = 1
        self.reference = self.bridge.get_object_info(object_name=self.source.Name)['object']['object_reference']
        self.app.flags['shared_source_curve'] = True
        failure = self.error(self.apply)
        self.assertTrue(failure.details['ownership_uncertain'])
        self.assertNotIn(self.source.StaticID, self.app.deleted)

    def test_changed_duplicate_and_ignored_conversion_discard_only_owned_copy(self):
        self.app.flags['duplicate_geometry'] = True
        failure = self.error(self.apply)
        self.assertTrue(failure.details['rollback']['verified'])
        self.assertEqual(self.layer.Shapes.items, self.baseline)
        self.setUp(); self.source.Type = 1
        self.reference = self.bridge.get_object_info(object_name=self.source.Name)['object']['object_reference']
        self.app.flags['ignore_conversion'] = True
        self.assertTrue(self.error(self.apply).details['rollback']['verified'])

    def test_ignored_native_controls_are_detected_and_owned_outputs_discarded(self):
        for name, value in (('Direction', 0), ('Offset', .2), ('Steps', 2), ('ColorBlendType', 1), ('EndCapType', 2),
                            ('CornerType', 1), ('MiterLimit', 5.), ('SpacingAcceleration', 1), ('ColorAcceleration', 1)):
            self.setUp(); self.app.flags['parameter_changes'] = {name: value}
            failure = self.error(self.apply)
            self.assertEqual(failure.code, ErrorCode.COREL_COM_ERROR)
            self.assertTrue(failure.details['rollback']['verified'])
            self.assertEqual(self.layer.Shapes.items, self.baseline)

    def test_native_parameter_type_and_color_mismatches_fail(self):
        for changes in ({'Direction': True}, {'Offset': float('nan')}, {'FillColor': native_color(cmyk())}):
            self.setUp(); self.app.flags['parameter_changes'] = changes
            self.assertTrue(self.error(self.apply).details['rollback']['verified'])

    def test_wrong_parent_or_effect_type_is_not_reported_as_success(self):
        for flag in ('wrong_parent', 'wrong_effect_type'):
            self.setUp(); self.app.flags[flag] = True
            self.assertEqual(self.error(self.apply).code, ErrorCode.COREL_COM_ERROR)
            self.assertNotIn(self.source.StaticID, self.app.deleted)

    def test_foreign_descendants_and_aliased_generated_curves_quarantine_cleanup(self):
        for flag in ('foreign_child', 'shared_generated_curve'):
            self.setUp(); self.app.flags[flag] = True
            failure = self.error(self.apply)
            self.assertTrue(failure.details['ownership_uncertain'])
            self.assertFalse(failure.details['rollback']['verified'])
            self.assertNotIn(self.app.other_source.StaticID, self.app.deleted)

    def test_unaccounted_native_roots_are_not_deleted(self):
        self.app.flags['unknown_created_root'] = True
        failure = self.error(self.apply)
        self.assertTrue(failure.details['ownership_uncertain'])
        self.assertFalse(failure.details['rollback']['verified'])
        self.assertTrue(any(s.Name == 'UnknownNativeRoot' for s in self.layer.Shapes.items))

    def test_separation_and_ungrouping_preserve_measured_curve_geometry(self):
        for flag in ('separate_geometry', 'separate_failure', 'ungroup_failure'):
            self.setUp(); self.app.flags[flag] = True
            failure = self.error(self.apply)
            self.assertTrue(failure.details['rollback']['verified'])
            self.assertEqual(self.layer.Shapes.items, self.baseline)

    def test_foreign_separation_receipt_is_rejected_without_source_deletion(self):
        self.app.flags['separate_foreign_receipt'] = True
        failure = self.error(self.apply)
        self.assertTrue(failure.details['ownership_uncertain'])
        self.assertNotIn(self.source.StaticID, self.app.deleted)

    def test_final_color_outline_transparency_and_geometry_changes_fail(self):
        for flag in ('ignore_fill', 'ignore_outline', 'ignore_transparency', 'corrupt_style_geometry', 'style_failure'):
            self.setUp(); self.app.flags[flag] = True
            failure = self.error(self.apply)
            self.assertTrue(failure.details['rollback']['verified'])
            self.assertEqual(self.layer.Shapes.items, self.baseline)

    def test_source_corruption_and_failed_cleanup_prevent_verified_rollback(self):
        self.app.flags['source_corruption'] = True
        self.assertFalse(self.error(self.apply).details['rollback']['verified'])
        self.setUp(); self.app.flags.update(create_failure=True, fail_delete=True)
        self.assertFalse(self.error(self.apply).details['rollback']['verified'])

    def test_late_native_creation_failure_recovers_proven_owned_affiliates(self):
        self.app.flags['create_late_failure'] = True
        failure = self.error(self.apply)
        self.assertTrue(failure.details['rollback']['verified'])
        self.assertEqual(self.layer.Shapes.items, self.baseline)
        self.assertNotIn(self.source.StaticID, self.app.deleted)

    def test_closed_target_never_falls_back(self):
        self.app.Documents.items = []
        self.assertEqual(self.error(self.apply).code, ErrorCode.NO_TARGET_DOCUMENT)
        self.assertEqual(self.app.duplicates, [])

    def test_owned_leaves_straying_outside_the_layer_cannot_claim_verified_cleanup(self):
        self.app.flags['stray_leaf_failure'] = True
        failure = self.error(self.apply)
        self.assertFalse(failure.details['rollback']['verified'])
        self.assertTrue(failure.details['ownership_uncertain'])
        self.assertNotIn(self.app.stray.StaticID, self.app.deleted)

    def test_owned_controller_straying_after_creation_failure_requires_recovery(self):
        self.app.flags.update(create_late_failure=True, stray_controller=True)
        failure = self.error(self.apply)
        self.assertFalse(failure.details['rollback']['verified'])
        self.assertTrue(failure.details['ownership_uncertain'])
        self.assertNotIn(self.app.stray.StaticID, self.app.deleted)

    def test_failed_native_work_quarantines_writes_while_geometry_inspection_survives(self):
        self.app.flags.update(create_late_failure=True, unknown_created_root=True)
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                result = server.create_contour_offsets(self.reference, .1)
                self.assertFalse(result['ok']); self.assertNotIn('secret', str(result))
                self.assertEqual(server.rotate_object(20, object_name=self.source.Name)['error']['code'], 'RECOVERY_REQUIRED')
                self.assertTrue(server.get_curve_geometry(object_reference=self.reference)['ok'])
        finally:
            dispatcher.close()

    def test_registered_schemas_and_results_are_strict(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(t for t in registry['tools'] if t['name'] == 'create_contour_offsets')
        validator = Draft202012Validator({'schema_definitions': registry['schema_definitions'], **tool['input_schema']})
        validator.validate({'object_reference': self.reference, 'offset_inches': .1})
        for extra in ({'offset_inches': 0}, {'offset_inches': True}, {'steps': 33}, {'steps': True}, {'direction': 'center'}):
            with self.assertRaises(ValidationError):
                validator.validate({'object_reference': self.reference, 'offset_inches': .1, **extra})
        validator = Draft202012Validator({'schema_definitions': registry['schema_definitions'], **tool['output_schema']})
        result = self.apply(); validator.validate(success_result('create_contour_offsets', result, 1))
        invalid = copy.deepcopy(result); invalid['unexpected'] = True
        with self.assertRaises(ValidationError):
            validator.validate(success_result('create_contour_offsets', invalid, 1))
        self.setUp()
        self.app.flags['parameter_changes'] = {'Offset': .0001 - 1e-9, 'MiterLimit': 100. + 1e-9}
        rounded = self.apply(.0001, miter_limit=100.)
        self.assertLess(rounded['native_parameters']['Offset'], .0001)
        self.assertGreater(rounded['native_parameters']['MiterLimit'], 100.)
        validator.validate(success_result('create_contour_offsets', rounded, 1))


if __name__ == '__main__':
    unittest.main()
