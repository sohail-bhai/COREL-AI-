from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result
from gradient_fakes import Fill
from test_layout import Collection
import test_process_colors as process_fakes
from test_process_colors import cmyk, rgb, native_color
from test_transparency import Transparency


def stops(model='cmyk', middle=False):
    colors = [cmyk(0, 20, 40, 0), cmyk(10, 30, 50, 0), cmyk(40, 60, 80, 10)] if model == 'cmyk' else [rgb(), {'model': 'rgb', 'red': 90, 'green': 120, 'blue': 150}, {'model': 'rgb', 'red': 220, 'green': 240, 'blue': 255}]
    return [{'position_percent': p, 'color': c} for p, c in zip((0, 40, 100) if middle else (0, 100), colors if middle else (colors[0], colors[-1]))]


class GradientTests(unittest.TestCase):
    def setUp(self):
        fixture = process_fakes.ProcessColorTests()
        fixture.setUp()
        self.app, self.document, self.source, self.bridge, self.reference = fixture.app, fixture.document, fixture.source, fixture.bridge, fixture.reference
        self.source.Fill = Fill(self.source)
        self.fill = self.source.Fill
        self.source.Transparency = Transparency(self.source)

    def apply(self, value=None, **kwargs):
        return self.bridge.set_gradient_fill(stops() if value is None else value, object_reference=self.reference, **kwargs)

    def inspect(self):
        return self.bridge.get_gradient_fill(object_reference=self.reference)

    def error(self, call, *args, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            call(*args, **kwargs)
        return caught.exception

    def test_absent_gradient_inspection_is_read_only_and_complete(self):
        value = self.inspect()
        self.assertIsNone(value['fill']['gradient'])
        self.assertTrue(value['fill']['complete'])
        self.assertEqual(len(value['fingerprint']), 64)
        self.assertEqual(self.fill.calls, [])

    def test_cmyk_multistop_gradients_preserve_geometry_and_other_channels(self):
        before = self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
        outline = self.bridge._outline_readback(self.source)
        result = self.apply(stops(middle=True), angle_degrees=37., steps=128, edge_padding_percent=8)
        actual = result['fill']['gradient']
        self.assertEqual([s['position_percent'] for s in actual['stops']], [0, 40, 100])
        self.assertEqual([s['color']['value'] for s in actual['stops']], [{k: v for k, v in s['color'].items() if k != 'model'} for s in stops(middle=True)])
        self.assertEqual(actual['angle_degrees'], 37.)
        self.assertEqual(actual['steps'], 128)
        self.assertEqual(actual['edge_padding_percent'], 8)
        self.assertEqual(self.bridge.get_curve_geometry(object_reference=self.reference)['curve'], before)
        self.assertEqual(self.bridge._outline_readback(self.source), outline)
        self.assertTrue(result['preservation_verified'])
        self.assertEqual(self.document.Unit, 3)
        self.assertEqual(self.document.ReferencePoint, 9)

    def test_rgb_two_stops_use_exact_native_models_and_components(self):
        result = self.apply(stops('rgb'))
        self.assertEqual([s['color']['model'] for s in result['fill']['gradient']['stops']], ['rgb', 'rgb'])

    def test_four_native_types_offsets_and_angle_normalization(self):
        for kind in ('linear', 'radial', 'conical', 'square'):
            self.setUp()
            actual = self.apply(gradient_type=kind, angle_degrees=-45., center_offset_x_percent=20., center_offset_y_percent=-10.)['fill']['gradient']
            self.assertEqual(actual['type'], kind)
            self.assertEqual(actual['angle_degrees'], 315.)
            self.assertEqual(actual['center_offset_x_percent'], 20.)
            self.assertEqual(actual['center_offset_y_percent'], -10.)
            self.assertFalse(actual['is_transparent'])
            self.assertFalse(actual['anisotropic'])
            self.assertEqual(actual['spread_method_code'], 0)

    def test_existing_gradient_revision_requires_current_fingerprint(self):
        self.apply()
        fingerprint = self.inspect()['fingerprint']
        self.assertEqual(self.error(self.apply).code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.error(self.apply, expected_fingerprint='0' * 64).code, ErrorCode.INVALID_ARGUMENT)
        result = self.apply(stops(middle=True), expected_fingerprint=fingerprint)
        self.assertEqual(result['before_fingerprint'], fingerprint)
        self.assertNotEqual(result['fingerprint'], fingerprint)

    def test_changed_native_stop_parameters_invalidate_fingerprint(self):
        self.apply()
        fingerprint = self.inspect()['fingerprint']
        self.fill.Fountain.Colors.items[0].Color.CMYKBlack = 60
        self.assertEqual(self.error(self.apply, expected_fingerprint=fingerprint).code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(len(self.fill.calls), 1)

    def test_other_fill_replacement_requires_explicit_intent(self):
        self.fill.Type = 9
        self.assertEqual(self.error(self.apply).code, ErrorCode.INVALID_ARGUMENT)
        self.assertTrue(self.apply(replace_existing=True)['updated'])

    def test_stop_ranges_fields_models_and_order_are_rejected_before_writes(self):
        invalid = [[], stops()[:1], stops() * 17, list(reversed(stops())), stops() + [stops()[1]],
                   [{'position_percent': True, 'color': rgb()}, stops()[1]],
                   [{'position_percent': 0.5, 'color': rgb()}, stops()[1]],
                   [{'position_percent': 0, 'color': rgb()}, stops()[1]],
                   [{**stops()[0], 'opacity': 50}, stops()[1]],
                   [{'position_percent': 0, 'color': cmyk(k=101)}, stops()[1]],
                   [{'position_percent': -1, 'color': cmyk()}, stops()[1]]]
        for value in invalid:
            self.assertEqual(self.error(self.apply, value).code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.fill.calls, [])

    def test_invalid_gradient_parameters_fail_before_writes(self):
        for kwargs in ({'gradient_type': 'mesh'}, {'gradient_type': True}, {'angle_degrees': float('nan')},
                       {'angle_degrees': 361.}, {'steps': 1}, {'steps': True}, {'steps': 257},
                       {'edge_padding_percent': 50}, {'edge_padding_percent': 2.5},
                       {'center_offset_x_percent': -51.}, {'center_offset_y_percent': float('inf')},
                       {'replace_existing': 1}, {'expected_fingerprint': None}):
            self.assertEqual(self.error(self.apply, **kwargs).code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.fill.calls, [])

    def test_missing_getters_and_invalid_scalars_are_explicit(self):
        self.apply()
        del self.fill.Fountain.SpreadMethod
        self.fill.Fountain.Angle = float('nan')
        value = self.inspect()
        self.assertFalse(value['fill']['complete'])
        self.assertIsNone(value['fingerprint'])
        self.assertIn('SpreadMethod', value['fill']['unavailable_properties'])
        self.assertIn('Angle', value['fill']['unavailable_properties'])
        self.assertEqual(self.error(self.apply, expected_fingerprint='0' * 64).code, ErrorCode.UNSUPPORTED_IN_PROFILE)

    def test_collection_limits_are_checked_before_enumeration(self):
        self.apply()
        class Huge:
            Count = 100000
            def Item(self, index):
                raise AssertionError('Must not enumerate oversized collections')
        self.fill.Fountain.Colors = Huge()
        self.assertFalse(self.inspect()['fill']['complete'])

    def test_missing_native_color_components_suppress_fingerprints(self):
        self.apply()
        del self.fill.Fountain.Colors.items[0].Color.CMYKMagenta
        result = self.inspect()
        self.assertFalse(result['fill']['complete'])
        self.assertIsNone(result['fingerprint'])
        self.assertIn('StopColor', result['fill']['unavailable_properties'])

    def test_incomplete_outline_components_are_refused_before_writing(self):
        del self.source.Outline.Color.RGBGreen
        self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.fill.calls, [])

    def test_native_stop_order_and_endpoint_mismatches_are_incomplete(self):
        self.apply()
        self.fill.Fountain.Colors.items.reverse()
        self.assertFalse(self.inspect()['fill']['complete'])

    def test_aliased_color_factories_are_detected_before_assignment(self):
        shared = native_color(cmyk())
        def factory(c, m, y, k):
            shared.CMYKCyan, shared.CMYKMagenta, shared.CMYKYellow, shared.CMYKBlack = c, m, y, k
            return shared
        self.app.CreateCMYKColor = factory
        self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.fill.calls, [])

    def test_ignored_or_partial_creation_requires_recovery_without_automatic_undo(self):
        for flag in ('ignore', 'fail'):
            self.setUp()
            setattr(self.fill, flag, True)
            failure = self.error(self.apply)
            self.assertFalse(failure.details['rollback']['attempted'])
            self.assertTrue(failure.details['recovery_required'])
            self.assertNotIn('secret', str(failure))

    def test_ignored_intermediate_additions_are_not_reported_as_success(self):
        self.fill.after_create = lambda f: setattr(f.Colors, 'ignore_add', True)
        self.assertEqual(self.error(self.apply, stops(middle=True)).code, ErrorCode.COREL_COM_ERROR)

    def test_changed_intermediate_components_are_detected(self):
        self.fill.after_create = lambda f: setattr(f.Colors, 'convert_add', True)
        self.assertEqual(self.error(self.apply, stops(middle=True)).code, ErrorCode.COREL_COM_ERROR)

    def test_late_stop_removal_is_detected_in_final_readback(self):
        self.fill.drop_stop = True
        self.assertEqual(self.error(self.apply, stops(middle=True)).code, ErrorCode.COREL_COM_ERROR)

    def test_ignored_parameters_and_hidden_blends_fail(self):
        for name, value in (('Angle', 90.), ('CenterOffsetX', 1.), ('SmoothBlend', False), ('SpreadMethod', 2),
                            ('Anisotropic', True), ('MergeMode', 8), ('BlendAcceleration', 1.),
                            ('HasHSBBlends', True), ('HasNonLinearBlends', True)):
            self.setUp()
            self.fill.final_changes[name] = value
            self.assertEqual(self.error(self.apply).code, ErrorCode.COREL_COM_ERROR)

    def test_opaque_application_must_be_confirmed(self):
        self.fill.ignore_opaque = True
        self.assertEqual(self.error(self.apply).code, ErrorCode.COREL_COM_ERROR)

    def test_curve_and_outline_corruption_are_detected(self):
        for flag in ('mutate', 'corrupt_outline'):
            self.setUp()
            setattr(self.fill, flag, True)
            self.assertEqual(self.error(self.apply).code, ErrorCode.COREL_COM_ERROR)

    def test_uniform_transparency_is_preserved_and_changes_detected(self):
        self.source.Transparency.ApplyUniformTransparency(20)
        self.assertTrue(self.apply()['preservation_verified'])
        self.setUp()
        self.source.Transparency.ApplyUniformTransparency(20)
        self.fill.corrupt_transparency = True
        self.assertEqual(self.error(self.apply).code, ErrorCode.COREL_COM_ERROR)

    def test_unsupported_effects_and_outline_metadata_fail_before_writing(self):
        for field, value in (('transparency', 2), ('outline', 2), ('outline', None)):
            self.setUp()
            if field == 'transparency':
                self.source.Transparency.Type = value
            else:
                self.source.Outline.Type = value
            self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
            self.assertEqual(self.fill.calls, [])

    def text_fixture(self, linked=False):
        self.source.Type = 6
        self.source.Text = SimpleNamespace(Type=1, Frames=Collection(*([1, 2] if linked else [1])),
                                          Story=SimpleNamespace(Text='Editable title', Font='Arial', Size=18., Bold=-1))
        self.reference = self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']

    def test_editable_unlinked_text_is_preserved_and_story_changes_detected(self):
        self.text_fixture()
        before = self.bridge._text_readback(self.source)
        self.assertTrue(self.apply()['preservation_verified'])
        self.assertEqual(self.bridge._text_readback(self.source), before)
        self.setUp(); self.text_fixture()
        self.fill.corrupt_text = True
        self.assertEqual(self.error(self.apply).code, ErrorCode.COREL_COM_ERROR)

    def test_linked_text_and_unsupported_targets_are_refused(self):
        self.text_fixture(linked=True)
        self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.setUp()
        for code in (5, 7):
            self.source.Type, self.source.Shapes = code, Collection()
            reference = self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']
            self.assertEqual(self.error(self.bridge.set_gradient_fill, stops(), object_reference=reference).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.fill.calls, [])

    def test_indeterminate_or_nonfinite_story_styles_fail_before_writing(self):
        for field, value in (('Font', ''), ('Size', float('nan')), ('Size', 0), ('Bold', -2)):
            self.setUp(); self.text_fixture()
            setattr(self.source.Text.Story, field, value)
            self.assertEqual(self.error(self.apply).code, ErrorCode.UNSUPPORTED_IN_PROFILE)
            self.assertEqual(self.fill.calls, [])

    def test_closed_target_never_falls_back_to_an_active_document(self):
        self.app.Documents.items = []
        self.assertEqual(self.error(self.apply).code, ErrorCode.NO_TARGET_DOCUMENT)
        self.assertEqual(self.fill.calls, [])

    def test_failed_assignments_quarantine_edits_while_inspection_remains_available(self):
        self.fill.fail = True
        with patch.object(server, 'CorelBridge', return_value=self.bridge):
            dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                result = server.set_gradient_fill(stops(), object_reference=self.reference)
                self.assertFalse(result['ok'])
                self.assertNotIn('secret', str(result))
                self.assertEqual(server.rotate_object(20, object_name='ProcessSource')['error']['code'], 'RECOVERY_REQUIRED')
                self.assertTrue(server.get_gradient_fill(object_reference=self.reference)['ok'])
        finally:
            dispatcher.close()

    def test_registered_gradient_schemas_and_results_are_strict(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tools = {t['name']: t for t in registry['tools']}
        validator = Draft202012Validator({'schema_definitions': registry['schema_definitions'], **tools['set_gradient_fill']['input_schema']})
        validator.validate({'stops': stops(), 'object_reference': self.reference})
        for invalid in ({'stops': []}, {'stops': stops(), 'steps': 1}, {'stops': stops(), 'edge_padding_percent': 50},
                        {'stops': [{**stops()[0], 'position_percent': True}, stops()[1]]}):
            with self.assertRaises(ValidationError):
                validator.validate(invalid)
        for name, result in (('get_gradient_fill', self.inspect()), ('set_gradient_fill', self.apply())):
            validator = Draft202012Validator({'schema_definitions': registry['schema_definitions'], **tools[name]['output_schema']})
            validator.validate(success_result(name, result, 1))
            invalid = copy.deepcopy(result); invalid['unexpected'] = 1
            with self.assertRaises(ValidationError):
                validator.validate(success_result(name, invalid, 1))


if __name__ == '__main__':
    unittest.main()
