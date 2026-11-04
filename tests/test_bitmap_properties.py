import copy
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from bitmap_fakes import Collection, fixture, nest
from corel_operator import server
from corel_operator.bitmap_geometry import affine_pixel_resolution
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result


class AffinePixelTests(unittest.TestCase):
    def corners(self, matrix, w=4, h=2):
        a, b, c, d, x, y = matrix
        return [{'x': a * u + c * v + x, 'y': b * u + d * v + y} for u, v in ((0, 0), (w, 0), (w, h), (0, h))]

    def test_axis_aligned_uses_physical_extent(self):
        matrix = [1, 0, 0, 1, 8, 10]
        result = affine_pixel_resolution(self.corners(matrix), 1200, 600, matrix)
        self.assertEqual(result['axis_dpi'], {'x': 300., 'y': 300.}); self.assertAlmostEqual(result['minimum_direction_dpi'], 300.)

    def test_rotation_preserves_resolution_instead_of_using_axis_aligned_bounds(self):
        for degrees in (30, 45, 90, 135, 180, 270):
            co, si = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
            matrix = [co, si, -si, co, 10, -5]
            result = affine_pixel_resolution(self.corners(matrix), 1200, 600, matrix)
            self.assertAlmostEqual(result['axis_dpi']['x'], 300.); self.assertAlmostEqual(result['axis_dpi']['y'], 300.)
            self.assertAlmostEqual(result['minimum_direction_dpi'], 300.)

    def test_nonuniform_scale_and_reflections(self):
        for matrix in ([2, 0, 0, .5, 0, 0], [-2, 0, 0, .5, 0, 0], [2, 0, 0, -.5, 0, 0]):
            result = affine_pixel_resolution(self.corners(matrix), 1200, 600, matrix)
            self.assertEqual(result['axis_dpi'], {'x': 150., 'y': 600.}); self.assertAlmostEqual(result['minimum_direction_dpi'], 150.)

    def test_skew_worst_direction_can_fail_when_both_pixel_axes_pass(self):
        matrix = [1, 0, 1, 1, 0, 0]
        result = affine_pixel_resolution(self.corners(matrix), 1200, 600, matrix)
        self.assertGreater(min(result['axis_dpi'].values()), 200.)
        self.assertAlmostEqual(result['minimum_direction_dpi'], 300 / ((1 + math.sqrt(5)) / 2))
        self.assertLess(result['minimum_direction_dpi'], 200.)

    def test_cyclic_start_and_reversed_winding_do_not_change_resolution(self):
        matrix = [1, 0, .3, 1, 4, 9]; points = self.corners(matrix)
        baseline = affine_pixel_resolution(points, 1200, 600, matrix)
        for start in range(4):
            for corners in (points[start:] + points[:start], list(reversed(points[start:] + points[:start]))):
                result = affine_pixel_resolution(corners, 1200, 600, matrix)
                self.assertEqual(result['axis_dpi'], baseline['axis_dpi'])
                self.assertEqual(result['minimum_direction_dpi'], baseline['minimum_direction_dpi'])

    def test_matrix_scale_is_not_applied_twice_to_placed_geometry(self):
        matrix = [2, 0, 0, 2, 0, 0]
        result = affine_pixel_resolution(self.corners(matrix), 1200, 600, matrix)
        self.assertEqual(result['axis_dpi'], {'x': 150., 'y': 150.})

    def test_non_parallelogram_degenerate_and_unclear_axes_are_refused(self):
        matrix = [1, 0, 0, 1, 0, 0]; corners = self.corners(matrix)
        bad = copy.deepcopy(corners); bad[2]['x'] += .1
        for points, transform in ((bad, matrix), (corners, [0, 0, 0, 1, 0, 0]),
            (corners, [1, 0, 1, 0, 0, 0]), (corners, [1, 1, -1, 1, 0, 0]), ([corners[0]] * 4, matrix)):
            with self.assertRaises(ValueError): affine_pixel_resolution(points, 1200, 600, transform)

    def test_missing_nonfinite_or_boolean_pixel_grid_data_is_refused(self):
        matrix = [1, 0, 0, 1, 0, 0]; corners = self.corners(matrix)
        for pixels in (0, True, 1.2, None):
            with self.assertRaises(ValueError): affine_pixel_resolution(corners, pixels, 600, matrix)
        for points in ([], [{}] * 4, [{'x': float('nan'), 'y': 0}] * 4, [{'x': True, 'y': 0}] * 4):
            with self.assertRaises(ValueError): affine_pixel_resolution(points, 1200, 600, matrix)

    def test_small_non_affine_boxes_and_unresolvable_far_origin_precision_are_refused(self):
        matrix = [1, 0, 0, 1, 0, 0]
        corners = [{'x': 0., 'y': 0.}, {'x': 1e-9, 'y': 0.}, {'x': 1e-9, 'y': 2e-9}, {'x': 0., 'y': 1e-9}]
        with self.assertRaises(ValueError): affine_pixel_resolution(corners, 1200, 600, matrix)
        matrix = [1, 0, 0, 1, 1e6, 1e6]
        with self.assertRaises(ValueError): affine_pixel_resolution(self.corners(matrix, 1e-9, 1e-9), 1200, 600, matrix)


class BitmapPropertyTests(unittest.TestCase):
    def setUp(self):
        self.bridge, self.doc, self.shape, self.reference = fixture()

    def inspect(self, **kwargs):
        return self.bridge.get_bitmap_properties(object_reference=self.reference, **kwargs)

    def indeterminate(self, reason):
        result = self.inspect(); effective = result['effective_resolution']
        self.assertEqual(effective['status'], 'indeterminate'); self.assertEqual(effective['resolution_check'], 'not_checked')
        self.assertIsNone(effective['minimum_direction_dpi']); self.assertIn(reason, effective['reasons'])
        return result

    def test_native_metadata_is_separate_from_calculated_placed_resolution(self):
        result = self.inspect(); self.assertEqual(result['bitmap']['native_resolution'], {'x': 72, 'y': 72})
        self.assertEqual(result['bitmap']['size_pixels'], {'width': 1200, 'height': 600})
        self.assertEqual(result['effective_resolution']['axis_dpi'], {'x': 300., 'y': 300.})
        self.assertEqual(result['effective_resolution']['resolution_check'], 'pass')
        self.assertTrue(result['bitmap']['can_be_cropped']); self.assertFalse(result['bitmap']['crop_envelope_modified'])

    def test_threshold_comparison_uses_unrounded_worst_direction(self):
        self.assertEqual(self.inspect(minimum_dpi=300.)['effective_resolution']['resolution_check'], 'pass')
        self.assertEqual(self.inspect(minimum_dpi=300.00001)['effective_resolution']['resolution_check'], 'below_requested')

    def test_rotated_native_bbox_uses_oriented_pixel_axes(self):
        self.shape.matrix = [math.sqrt(.5), math.sqrt(.5), -math.sqrt(.5), math.sqrt(.5), 2, 3]
        result = self.inspect()
        self.assertAlmostEqual(result['effective_resolution']['minimum_direction_dpi'], 300.)
        self.assertNotAlmostEqual(result['bitmap']['size_pixels']['height'] / result['transform']['bounds_inches']['height'], 300.)

    def test_skew_below_requested_is_detected_despite_both_axis_dpi_passing(self):
        self.shape.matrix = [1, 0, 1, 1, 0, 0]
        result = self.inspect(minimum_dpi=200.)['effective_resolution']
        self.assertGreater(min(result['axis_dpi'].values()), 200.); self.assertEqual(result['resolution_check'], 'below_requested')

    def test_crop_retains_uncropped_grid_resolution_and_does_not_invent_detail(self):
        self.shape.Bitmap.CropEnvelopeModified = True; self.shape.crop_bounds = (.5, .25, 1, 1)
        result = self.inspect()
        self.assertEqual(result['effective_resolution']['axis_dpi'], {'x': 300., 'y': 300.})
        self.assertEqual(result['uncropped_box']['bounds_inches']['width'], 4.)
        self.assertEqual(result['transform']['bounds_inches']['width'], 1.)

    def test_crop_outside_grid_is_indeterminate(self):
        self.shape.Bitmap.CropEnvelopeModified = True; self.shape.crop_bounds = (-1, 0, 5, 2)
        self.indeterminate('crop_bounds_outside_uncropped_pixel_grid')

    def test_uncropped_bounds_mismatch_is_indeterminate(self):
        self.shape.crop_bounds = (0, 0, 3, 2)
        self.indeterminate('uncropped_box_disagrees_with_placed_bounds')

    def test_readback_pixel_count_change_during_inspection_prevents_resolution_pass(self):
        original = type(self.shape.Bitmap)
        class ChangingBitmap(original):
            reads = 0
            @property
            def BoundingBoxPath(self):
                self.reads += 1
                if self.reads == 1: self.SizeWidth += 1
                return super().BoundingBoxPath
        self.shape.Bitmap.__class__ = ChangingBitmap
        result = self.indeterminate('native_bitmap_state_changed_during_inspection')
        self.assertEqual(result['inspection_consistency']['status'], 'changed')

    def test_readback_scope_change_prevents_resolution_pass(self):
        original = type(self.shape.Bitmap)
        class ChangingBitmap(original):
            reads = 0
            @property
            def BoundingBoxPath(self):
                self.reads += 1
                if self.reads == 2: self.shape.Effects = Collection(object())
                return super().BoundingBoxPath
        self.shape.Bitmap.__class__ = ChangingBitmap
        self.indeterminate('native_bitmap_state_changed_during_inspection')

    def test_success_requires_two_native_geometry_reads_to_reconcile(self):
        result = self.inspect()
        self.assertEqual(result['inspection_consistency']['status'], 'two_reads_reconciled')
        self.assertEqual(result['effective_resolution']['resolution_check'], 'pass')

    def test_document_closing_during_native_readback_cannot_return_resolution_success(self):
        original = type(self.shape.Bitmap)
        class ClosingBitmap(original):
            reads = 0
            @property
            def BoundingBoxPath(bitmap):
                bitmap.reads += 1
                if bitmap.reads == 2: self.bridge.app.Documents.items.clear()
                return super().BoundingBoxPath
        self.shape.Bitmap.__class__ = ClosingBitmap
        with self.assertRaises(CorelBridgeError) as caught: self.inspect()
        self.assertEqual(caught.exception.code, ErrorCode.NO_TARGET_DOCUMENT)

    def test_unavailable_crop_state_is_indeterminate(self):
        del self.shape.Bitmap.CropEnvelopeModified
        result = self.indeterminate('unavailable_crop_envelope_state')
        self.assertIn('CropEnvelopeModified', result['bitmap']['unavailable_properties'])

    def test_native_missing_optional_fields_remain_explicit_without_blocking_geometry(self):
        del self.shape.Bitmap.ResolutionX; self.shape.Bitmap.Mode = True; del self.shape.Bitmap.Embedded
        result = self.inspect(); self.assertIsNone(result['bitmap']['native_resolution']['x'])
        self.assertIsNone(result['bitmap']['mode_code']); self.assertIsNone(result['bitmap']['embedded'])
        self.assertEqual(result['effective_resolution']['status'], 'calculated')

    def test_invalid_or_oversized_pixel_dimensions_are_indeterminate(self):
        for value in (None, True, 0, 1.2, 1_000_001):
            self.shape.Bitmap.SizeWidth = value; self.indeterminate('unavailable_pixel_dimensions')
        self.shape.Bitmap.SizeWidth = 100_000; self.shape.Bitmap.SizeHeight = 100_000
        self.indeterminate('pixel_dimensions_exceed_500_million_budget')

    def test_missing_bitmap_payload_is_explicit(self):
        self.shape.Bitmap = None
        result = self.indeterminate('unavailable_pixel_dimensions'); self.assertFalse(result['bitmap']['available'])

    def test_unreadable_native_bbox_is_redacted_and_indeterminate(self):
        self.shape.Bitmap.fail_box = True
        result = self.indeterminate('unavailable_complete_uncropped_box')
        self.assertNotIn('Private', json.dumps(result)); self.assertNotIn('secret', json.dumps(result))

    def test_native_box_counts_cubic_edges_aliases_and_connectivity_are_refused(self):
        for kind in ('count', 'cubic', 'alias', 'connectivity', 'owner'):
            curve = self.shape.Bitmap.BoundingBoxPath; path = curve.paths[0]
            if kind == 'count': path.nodes.append(path.nodes[0])
            if kind == 'cubic': path.segments[0].Type = 1
            if kind == 'alias': path.nodes[1] = path.nodes[0]
            if kind == 'connectivity': path.segments[0].EndNode = path.nodes[3]
            if kind == 'owner': path.nodes[0].SubPath = object()
            self.shape.Bitmap.override_box = curve
            self.indeterminate('unavailable_complete_uncropped_box')

    def test_malformed_quad_and_axis_mapping_are_indeterminate(self):
        curve = self.shape.Bitmap.BoundingBoxPath; curve.paths[0].nodes[2].PositionX += .1
        self.shape.Bitmap.override_box = curve
        self.shape.crop_bounds = (0, 0, 4.1, 2)
        self.indeterminate('non_affine_uncropped_box')

    def test_effects_clipping_or_unavailable_effect_scope_are_indeterminate(self):
        self.shape.Effects = Collection(object()); self.indeterminate('bitmap_or_ancestor_effects')
        self.shape.Effects = Collection(); self.shape.PowerClip = object(); self.indeterminate('bitmap_or_ancestor_clipping')
        self.shape.PowerClip = None; del self.shape.Effects; self.indeterminate('unavailable_bitmap_or_ancestor_effect_scope')

    def test_nested_group_native_scope_is_checked(self):
        parent = nest(self.shape); self.reference = self.bridge._reference_for_shape(self.doc, self.shape)
        self.assertEqual(self.inspect()['effective_resolution']['status'], 'calculated')
        parent.Effects = Collection(object()); self.indeterminate('bitmap_or_ancestor_effects')
        parent.Effects = Collection(); parent.PowerClip = object(); self.indeterminate('bitmap_or_ancestor_clipping')

    def test_signed_reference_and_legacy_selector_inspection_agree(self):
        result = self.bridge.get_bitmap_properties(object_name=self.shape.Name)
        self.assertEqual(result, self.inspect())

    def test_wrong_type_stale_reference_and_foreign_document_refuse(self):
        self.shape.Type = 3
        with self.assertRaises(CorelBridgeError): self.inspect()
        self.shape.Type = 5; self.shape.Name = 'Replaced'
        with self.assertRaises(CorelBridgeError) as caught: self.inspect()
        self.assertEqual(caught.exception.code, ErrorCode.OBJECT_NOT_FOUND)
        self.shape.Name = 'Bitmap'; self.bridge.app.Documents.items.clear()
        with self.assertRaises(CorelBridgeError) as caught: self.inspect()
        self.assertEqual(caught.exception.code, ErrorCode.NO_TARGET_DOCUMENT)

    def test_malformed_thresholds_refuse_before_native_inspection(self):
        for value in (0, True, None, '300', float('nan'), float('inf'), 2401):
            with self.assertRaises(CorelBridgeError) as caught: self.inspect(minimum_dpi=value)
            self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.shape.writes, [])

    def test_fingerprint_is_stable_and_changes_with_placement_pixels_metadata_and_threshold(self):
        first = self.inspect()['fingerprint']; self.assertEqual(first, self.inspect()['fingerprint'])
        self.assertNotEqual(first, self.inspect(minimum_dpi=200)['fingerprint'])
        self.shape.matrix[0] = 2; second = self.inspect()['fingerprint']; self.assertNotEqual(first, second)
        self.shape.Bitmap.SizeWidth = 1400; third = self.inspect()['fingerprint']; self.assertNotEqual(second, third)
        self.shape.Bitmap.ExternallyLinked = True; self.assertNotEqual(third, self.inspect()['fingerprint'])

    def test_inspection_preserves_object_and_context_and_contains_no_native_pointer_strings(self):
        before = (self.doc.Unit, self.doc.ReferencePoint, tuple(self.shape.matrix), self.shape.Bitmap.SizeWidth)
        result = self.inspect()
        self.assertEqual(before, (self.doc.Unit, self.doc.ReferencePoint, tuple(self.shape.matrix), self.shape.Bitmap.SizeWidth))
        self.assertEqual(self.shape.writes, []); self.assertNotIn('python:', json.dumps(result)); self.assertNotIn('iunknown:', json.dumps(result))

    def test_ignored_unit_or_reference_entry_and_restore_cannot_return_success(self):
        original_type = type(self.doc)
        class ContextDocument(original_type):
            block = None
            def __setattr__(self, key, value):
                if self.block == (key, value): return
                super().__setattr__(key, value)
        self.doc.__class__ = ContextDocument
        original = self.doc.Unit, self.doc.ReferencePoint
        for blocked in (('Unit', self.bridge.CDR_INCH), ('ReferencePoint', self.bridge.CDR_BOTTOM_LEFT), ('Unit', original[0]), ('ReferencePoint', original[1])):
            self.doc.block = None; self.doc.Unit, self.doc.ReferencePoint = original
            self.doc.block = blocked
            with self.assertRaises(CorelBridgeError): self.inspect()

    def test_server_recorded_wrapper_dispatches_exact_arguments(self):
        with patch.object(server, '_tool', return_value={'ok': True}) as tool:
            self.assertTrue(server.get_bitmap_properties(200., object_reference=self.reference)['ok'])
            tool.assert_called_once_with('get_bitmap_properties', 'get_bitmap_properties', 200., '', 0, self.reference)

    def test_bitmap_inspection_remains_available_when_native_writes_are_quarantined(self):
        with patch.object(server, 'CorelBridge', return_value=self.bridge): dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher), patch.object(self.bridge, 'draw_rectangle', side_effect=CorelBridgeError(
                'Native edit failed.', ErrorCode.COREL_COM_ERROR, {'rollback': {'verified': False}})):
                self.assertFalse(server.draw_rectangle(0, 0, 1, 1)['ok'])
                self.assertTrue(server.get_bitmap_properties(object_reference=self.reference)['ok'])
                self.assertEqual(server.activate_page('unknown', '0' * 64)['error']['code'], 'RECOVERY_REQUIRED')
        finally: dispatcher.close()

    def test_registered_input_output_schemas_validate_real_data_and_reject_coercion(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(t for t in registry['tools'] if t['name'] == 'get_bitmap_properties')
        inputs = Draft202012Validator({'schema_definitions': registry['schema_definitions'], **tool['input_schema']})
        inputs.validate({'object_reference': self.reference})
        for request in ({'minimum_dpi': True}, {'minimum_dpi': 2401}, {'unexpected': 'x'}, {'shape_index': True}):
            with self.assertRaises(ValidationError): inputs.validate({'object_reference': self.reference, **request})
        output = Draft202012Validator({'schema_definitions': registry['schema_definitions'], **tool['output_schema']})
        output.validate(success_result('get_bitmap_properties', self.inspect(), 1))
        self.shape.Bitmap.fail_box = True; output.validate(success_result('get_bitmap_properties', self.inspect(), 1))


if __name__ == '__main__': unittest.main()
