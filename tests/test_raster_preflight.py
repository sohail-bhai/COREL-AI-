from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.raster_preflight import local_link_presence
from corel_operator.results import success_result
from raster_preflight_fakes import Collection, Shape, fixture, group, clip


class RasterPreflightTests(unittest.TestCase):
    def setUp(self):
        self.bridge, self.doc, self.front, self.back = fixture()
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def inspect(self, **kwargs):
        return self.bridge.preflight_document_rasters(**kwargs)

    def codes(self, result):
        return {issue['code'] for issue in result['coverage']['issues']}

    def mutate_between_scans(self, change):
        scan = self.bridge._raster_scan; calls = 0
        def changed(*args):
            nonlocal calls
            result = scan(*args); calls += 1
            if calls == 1: change()
            return result
        with patch.object(self.bridge, '_raster_scan', side_effect=changed): return self.inspect()

    def linked(self, filename):
        self.front.Bitmap.ExternallyLinked = True; self.front.Bitmap.LinkFileName = str(filename)

    def test_all_pages_checked_without_activation(self):
        result = self.inspect()
        self.assertEqual(result['summary'], {'passed': 2, 'failed': 0, 'indeterminate': 0, 'total': 2})
        self.assertEqual([row['location']['page_index'] for row in result['rasters']], [1, 2])
        self.assertEqual(result['coverage']['status'], 'complete')
        self.assertEqual(result['inspection_consistency']['status'], 'two_scans_reconciled')
        self.assertTrue(result['raster_checks_passed']); self.assertFalse(result['production_ready'])
        self.assertEqual(self.doc.calls, []); self.assertEqual(self.front.writes, [])
        self.assertEqual((self.doc.Unit, self.doc.ReferencePoint, self.doc.Dirty), (3, 9, False))
        self.assertIs(self.doc.ActivePage, self.doc.Pages.items[0])
        self.assertNotIn('python:', json.dumps(result)); self.assertNotIn('iunknown:', json.dumps(result))

    def test_low_resolution_on_inactive_page_fails(self):
        self.back.Bitmap.SizeWidth = 300
        result = self.inspect()
        self.assertEqual(result['summary']['failed'], 1); self.assertEqual(result['overall_status'], 'failed')
        self.assertEqual(result['rasters'][1]['checks']['effective_resolution'], 'failed')
        self.assertIs(self.doc.ActivePage, self.doc.Pages.items[0])

    def test_nested_groups_are_checked_with_scope(self):
        parent = group([self.back]); grandparent = group([parent], static_id=802)
        result = self.inspect()
        row = result['rasters'][1]
        self.assertEqual(row['status'], 'passed')
        self.assertEqual([step['kind'] for step in row['location']['path']], ['root', 'group', 'group'])
        self.assertEqual(result['coverage']['accessed_shapes'], 4)
        self.assertEqual(grandparent.writes, [])

    def test_group_effects_remain_indeterminate(self):
        parent = group([self.back]); parent.Effects = Collection(SimpleNamespace())
        result = self.inspect()
        self.assertEqual(result['overall_status'], 'indeterminate')
        self.assertIn('bitmap_or_ancestor_effects', result['rasters'][1]['reasons'])

    def test_unreadable_ancestor_transform_invalidates_child_resolution(self):
        parent = group([self.front]); snapshot = self.bridge._layout_snapshot
        def unreadable(document, shape):
            if shape is parent: raise CorelBridgeError('Native transform unavailable.', ErrorCode.COREL_COM_ERROR)
            return snapshot(document, shape)
        with patch.object(self.bridge, '_layout_snapshot', side_effect=unreadable): result = self.inspect()
        self.assertEqual(result['rasters'][0]['status'], 'indeterminate')
        self.assertIn('ancestor_transform_unreadable', result['rasters'][0]['reasons'])

    def test_powerclip_bitmap_is_found_without_editing_reference(self):
        frame = clip([self.back]); result = self.inspect()
        self.assertEqual(result['summary']['total'], 2)
        self.assertEqual(result['rasters'][1]['status'], 'indeterminate')
        self.assertEqual(result['rasters'][1]['location']['path'][-1]['kind'], 'powerclip')
        self.assertIn('bitmap_inside_powerclip_coordinate_scope', result['rasters'][1]['reasons'])
        self.assertEqual(frame.writes, [])

    def test_group_inside_clip_preserves_nested_scope(self):
        parent = group([self.back]); clip([parent])
        result = self.inspect()
        self.assertEqual([step['kind'] for step in result['rasters'][1]['location']['path']], ['root', 'powerclip', 'group'])
        self.assertEqual(result['rasters'][1]['status'], 'indeterminate')

    def test_master_bitmap_recorded_once_with_all_applied_pages(self):
        Shape(self.doc.MasterPage.ActiveLayer, 'Master bitmap', 701)
        result = self.inspect()
        self.assertEqual(result['summary']['total'], 3)
        row = result['rasters'][2]
        self.assertEqual(row['location']['scope'], 'master'); self.assertIsNone(row['location']['page_index'])
        self.assertEqual(row['location']['applies_to_page_indices'], [1, 2])
        self.assertEqual(row['status'], 'indeterminate')
        self.assertIn('master_bitmap_coordinate_mapping_not_verified', row['reasons'])

    def test_nonprinting_layers_excluded_explicitly(self):
        object.__setattr__(self.back.Layer, 'Printable', False)
        self.back.Bitmap.SizeWidth = 10
        result = self.inspect()
        self.assertEqual(result['summary']['total'], 1); self.assertTrue(result['raster_checks_passed'])
        self.assertEqual(result['coverage']['excluded_layers'][0]['reason'], 'nonprinting_layer')
        result = self.inspect(include_nonprinting=True)
        self.assertEqual(result['summary']['failed'], 1)

    def test_hidden_printable_layers_still_checked(self):
        object.__setattr__(self.back.Layer, 'Visible', False); self.back.Bitmap.SizeWidth = 10
        result = self.inspect()
        self.assertEqual(result['summary']['failed'], 1)
        self.assertFalse(result['rasters'][1]['location']['layer_visible'])

    def test_empty_scope_is_not_applicable(self):
        self.front.Layer.Shapes.items.clear(); self.back.Layer.Shapes.items.clear()
        result = self.inspect()
        self.assertEqual(result['overall_status'], 'not_applicable'); self.assertFalse(result['raster_checks_passed'])
        self.assertEqual(result['coverage']['status'], 'complete')

    def test_unreadable_bitmap_geometry_prevents_pass(self):
        self.front.Bitmap.fail_box = True
        result = self.inspect()
        self.assertEqual(result['summary']['indeterminate'], 1)
        self.assertFalse(result['raster_checks_passed'])

    def test_eps_placeholder_cannot_pass_resolution(self):
        self.front.Bitmap.IsEPS = True
        result = self.inspect()
        self.assertEqual(result['rasters'][0]['checks']['effective_resolution'], 'indeterminate')
        self.assertIn('eps_placeholder_resolution_not_final_raster', result['rasters'][0]['reasons'])

    def test_unknown_link_or_eps_flags_are_not_assumed_false(self):
        for name in ('OPILinked', 'IsEPS'):
            with self.subTest(name=name):
                old = getattr(self.front.Bitmap, name); delattr(self.front.Bitmap, name)
                self.assertEqual(self.inspect()['overall_status'], 'indeterminate')
                setattr(self.front.Bitmap, name, old)

    def test_local_link_presence_passes_without_reading_source_pixels(self):
        path = self.root / 'source.png'; path.write_bytes(b'presence only, intentionally not decodable')
        self.linked(path)
        result = self.inspect()
        self.assertEqual(result['rasters'][0]['checks']['linked_source_presence'], 'passed')
        self.assertEqual(result['rasters'][0]['link']['presence']['file_bytes'], path.stat().st_size)
        self.assertTrue(result['raster_checks_passed'])
        self.assertIn('native_link_cache_freshness', result['unchecked_checks'])

    def test_opi_mapping_and_unreadable_opi_cannot_claim_source_pass(self):
        path = self.root/'external.png'; path.write_bytes(b'presence'); self.linked(path)
        self.front.Bitmap.OPILinked = True
        self.assertIn('opi_source_mapping_requires_native_verification', self.inspect()['rasters'][0]['reasons'])
        del self.front.Bitmap.OPILinked
        self.assertIn('native_opi_link_state_unavailable', self.inspect()['rasters'][0]['reasons'])

    def test_native_link_filename_change_invalidates_snapshot(self):
        one = self.root/'one.png'; two = self.root/'two.png'
        one.write_bytes(b'presence'); two.write_bytes(b'presence'); self.linked(one)
        result = self.mutate_between_scans(lambda: setattr(self.front.Bitmap, 'LinkFileName', str(two)))
        self.assertEqual(result['inspection_consistency']['status'], 'changed')
        self.assertFalse(result['raster_checks_passed'])

    def test_missing_link_fails_with_object_evidence(self):
        self.linked(self.root / 'missing.png')
        result = self.inspect()
        row = result['rasters'][0]
        self.assertEqual(row['status'], 'failed'); self.assertIn('linked_source_missing', row['reasons'])
        self.assertEqual(row['location']['static_id'], self.front.StaticID)

    def test_empty_or_directory_link_fails_presence(self):
        empty = self.root / 'empty.png'; empty.touch()
        for path in (empty, self.root):
            with self.subTest(path=path):
                self.linked(path); self.assertEqual(self.inspect()['overall_status'], 'failed')

    def test_remote_links_not_accessed(self):
        self.linked('//server/share/image.png')
        with patch.object(Path, 'stat', side_effect=AssertionError('must not access network')):
            result = self.inspect()
        self.assertEqual(result['rasters'][0]['link']['presence']['status'], 'indeterminate')
        self.assertIn('remote_or_device_link_not_checked', result['rasters'][0]['reasons'])

    def test_relative_link_uses_candidate_base_without_native_pass(self):
        self.doc.FullFileName = str(self.root / 'document.cdr')
        source = self.root / 'image.png'; source.write_bytes(b'presence')
        self.linked('image.png')
        row = self.inspect()['rasters'][0]
        self.assertEqual(row['link']['presence']['resolved_path'], str(source))
        self.assertEqual(row['link']['presence']['status'], 'indeterminate')
        self.assertIn('relative_link_base_requires_native_verification', row['reasons'])

    def test_relative_link_unsaved_document_remains_indeterminate(self):
        self.linked('image.png')
        result = self.inspect()
        self.assertIn('relative_link_without_saved_document_base', result['rasters'][0]['reasons'])

    def test_link_stat_error_redacted(self):
        self.linked(self.root / 'image.png')
        with patch.object(Path, 'stat', side_effect=PermissionError('Private secret credential')):
            result = self.inspect()
        self.assertEqual(result['overall_status'], 'indeterminate')
        self.assertNotIn('Private', json.dumps(result)); self.assertNotIn('credential', json.dumps(result))

    def test_link_change_between_scans_invalidates_every_pass(self):
        path = self.root / 'image.png'; path.write_bytes(b'old'); self.linked(path)
        result = self.mutate_between_scans(lambda: path.write_bytes(b'longer changed file'))
        self.assertEqual(result['overall_status'], 'indeterminate')
        self.assertEqual(result['summary']['passed'], 0)
        self.assertEqual(result['summary']['indeterminate'], 2)
        self.assertEqual(result['rasters'][0]['observed_status'], 'passed')

    def test_native_metadata_and_placement_changes_invalidate_snapshot(self):
        changes = [lambda: setattr(self.front.Bitmap, 'SizeWidth', 10),
                   lambda: setattr(self.front.Bitmap, 'Mode', 6),
                   lambda: self.front.matrix.__setitem__(0, 2),
                   lambda: setattr(self.front.Bitmap, 'ExternallyLinked', True)]
        for change in changes:
            with self.subTest(change=change):
                result = self.mutate_between_scans(change)
                self.assertEqual(result['inspection_consistency']['status'], 'changed')
                self.assertFalse(result['raster_checks_passed'])
                self.front.Bitmap.SizeWidth = 1200; self.front.Bitmap.Mode = 5
                self.front.Bitmap.ExternallyLinked = False; self.front.matrix[0] = 1

    def test_changed_ancestor_transform_is_detected(self):
        parent = group([self.front])
        result = self.mutate_between_scans(lambda: parent.matrix.__setitem__(0, 2))
        self.assertIn('document_raster_state_changed_between_scans', self.codes(result))
        self.assertEqual(result['rasters'][0]['status'], 'indeterminate')

    def test_nested_order_and_membership_changes_are_detected(self):
        other = Shape(self.front.Layer, 'Other', 502); parent = group([self.front, other])
        result = self.mutate_between_scans(lambda: parent.Shapes.items.reverse())
        self.assertEqual(result['inspection_consistency']['status'], 'changed')
        self.assertFalse(result['raster_checks_passed'])

    def test_new_layer_flag_invalidates_scope(self):
        result = self.mutate_between_scans(lambda: object.__setattr__(self.back.Layer, 'Printable', False))
        self.assertFalse(result['raster_checks_passed']); self.assertEqual(result['coverage']['status'], 'partial')

    def test_shape_budget_returns_partial_coverage(self):
        result = self.inspect(max_shapes=1)
        self.assertEqual(result['coverage']['accessed_shapes'], 1)
        self.assertIn('shape_budget_exhausted', self.codes(result)); self.assertFalse(result['raster_checks_passed'])
        self.assertEqual(result['summary']['passed'], 1); self.assertEqual(result['overall_status'], 'indeterminate')

    def test_depth_limit_prevents_whole_scope_pass(self):
        parent = self.front
        for index in range(34): parent = group([parent], static_id=1000+index)
        result = self.inspect()
        self.assertIn('maximum_nesting_depth_exceeded', self.codes(result))
        self.assertFalse(result['raster_checks_passed'])

    def test_group_alias_or_cycle_is_reported(self):
        parent = group([self.front]); parent.Shapes.items.append(parent)
        result = self.inspect()
        self.assertIn('aliased_or_cyclic_shape_membership', self.codes(result))
        self.assertEqual(result['coverage']['status'], 'partial')

    def test_foreign_or_wrong_parent_membership_not_trusted(self):
        parent = group([self.front]); self.front.ParentGroup = self.back
        result = self.inspect()
        self.assertIn('inconsistent_parent_ownership', self.codes(result))
        self.assertEqual(result['summary']['total'], 1)
        self.front.ParentGroup = parent; self.front.Page = self.back.Page
        result = self.inspect()
        self.assertIn('foreign_shape_ownership', self.codes(result))

    def test_unreadable_child_getter_does_not_prove_absence(self):
        del self.front.PowerClip
        result = self.inspect()
        self.assertIn('native_child_membership_unreadable', self.codes(result))
        self.assertFalse(result['raster_checks_passed'])

    def test_symbol_ole_eps_custom_and_unknown_containers_prevent_clean_scope(self):
        for code in (0, 8, 12, 17, 21, 23, 24, 25, 27, 999):
            with self.subTest(code=code):
                opaque = Shape(self.front.Layer, 'Opaque', 999, code)
                result = self.inspect()
                self.assertIn('opaque_or_unknown_native_raster_container', self.codes(result))
                self.assertFalse(result['raster_checks_passed'])
                self.front.Layer.Shapes.items.remove(opaque)

    def test_special_effect_groups_enumerate_rasters_without_clean_scope(self):
        parent = group([self.front]); parent.Type = 10
        result = self.inspect()
        self.assertEqual(result['summary']['total'], 2)
        self.assertEqual(result['rasters'][0]['status'], 'indeterminate')
        self.assertIn('special_native_container_rendering_not_checked', self.codes(result))
        self.assertIn('special_native_effect_group_rendering_not_verified', result['rasters'][0]['reasons'])

    def test_context_dirty_selection_or_activation_changes_refuse(self):
        for change in (lambda: setattr(self.doc, 'Dirty', True), lambda: self.doc.SelectionRange.items.append(self.front),
                       lambda: setattr(self.doc, 'ActivePage', self.doc.Pages.items[1])):
            with self.subTest(change=change):
                with self.assertRaises(CorelBridgeError) as caught: self.mutate_between_scans(change)
                self.assertEqual(caught.exception.code, ErrorCode.COREL_COM_ERROR)
                self.doc.Dirty = False; self.doc.SelectionRange.items.clear(); self.doc.ActivePage = self.doc.Pages.items[0]

    def test_context_and_selection_must_be_readable(self):
        del self.doc.Dirty
        with self.assertRaises(CorelBridgeError) as caught: self.inspect()
        self.assertEqual(caught.exception.code, ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.doc.Unit, 3)

    def test_late_document_closure_refuses(self):
        with self.assertRaises(CorelBridgeError) as caught:
            self.mutate_between_scans(lambda: self.bridge.app.Documents.items.clear())
        self.assertEqual(caught.exception.code, ErrorCode.NO_TARGET_DOCUMENT)

    def test_invalid_arguments_refuse_before_native_context(self):
        cases = [{'minimum_dpi': True}, {'minimum_dpi': 0}, {'minimum_dpi': float('nan')},
                 {'minimum_dpi': 2401}, {'include_nonprinting': 1}, {'max_shapes': True}, {'max_shapes': 0}, {'max_shapes': 4097}]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(CorelBridgeError) as caught: self.inspect(**values)
            self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.doc.Unit, 3)

    def test_context_entry_and_restoration_failures_cannot_pass(self):
        for flag in ('ignore_inch_units', 'ignore_unit_restore'):
            bridge, doc, _, _ = fixture(); doc.flags[flag] = True
            with self.assertRaises(CorelBridgeError): bridge.preflight_document_rasters()

    def test_read_only_preflight_remains_available_during_write_quarantine(self):
        with patch.object(server, 'CorelBridge', return_value=self.bridge): dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher), patch.object(self.bridge, 'draw_rectangle', side_effect=CorelBridgeError(
                    'Native edit failed.', ErrorCode.COREL_COM_ERROR, {'rollback': {'verified': False}})):
                self.assertFalse(server.draw_rectangle(0, 0, 1, 1)['ok'])
                self.assertTrue(server.preflight_document_rasters()['ok'])
                self.assertEqual(server.activate_page('unknown', '0'*64)['error']['code'], 'RECOVERY_REQUIRED')
        finally: dispatcher.close()

    def test_recorded_server_dispatches_exact_arguments(self):
        with patch.object(server, '_tool', return_value={'ok': True}) as tool:
            server.preflight_document_rasters(200., True, 500)
            tool.assert_called_once_with('preflight_document_rasters', 'preflight_document_rasters', 200., True, 500)

    def test_context_failure_quarantines_subsequent_native_writes(self):
        scan = self.bridge._raster_scan
        def changed(*args):
            result = scan(*args); self.doc.Dirty = True; return result
        with patch.object(server, 'CorelBridge', return_value=self.bridge): dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher), patch.object(self.bridge, '_raster_scan', side_effect=changed):
                self.assertEqual(server.preflight_document_rasters()['error']['code'], 'COREL_COM_ERROR')
                self.assertEqual(server.draw_rectangle(0, 0, 1, 1)['error']['code'], 'RECOVERY_REQUIRED')
                self.assertTrue(server.get_document_structure()['ok'])
        finally: dispatcher.close()

    def test_fingerprint_stable_and_sensitive_to_threshold(self):
        result = self.inspect()
        self.assertEqual(result['fingerprint'], self.inspect()['fingerprint'])
        self.assertNotEqual(result['fingerprint'], self.inspect(minimum_dpi=200)['fingerprint'])

    def validators(self):
        registry = json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool = next(tool for tool in registry['tools'] if tool['name'] == 'preflight_document_rasters')
        return [Draft202012Validator({**tool[key+'_schema'], 'schema_definitions': registry['schema_definitions']}) for key in ('input', 'output')]

    def test_strict_schemas_validate_complete_partial_and_changed_outputs(self):
        _, output = self.validators()
        for result in (self.inspect(), self.inspect(max_shapes=1), self.mutate_between_scans(lambda: setattr(self.front.Bitmap, 'SizeWidth', 1))):
            output.validate(success_result('preflight_document_rasters', result, 1))

    def test_strict_schema_rejects_false_pass_and_unchecked_sources(self):
        _, output = self.validators()
        for edit in ('coverage', 'consistency', 'row', 'presence', 'production'):
            result = self.inspect()
            if edit == 'coverage': result['coverage']['status'] = 'partial'
            if edit == 'consistency': result['inspection_consistency']['status'] = 'changed'
            if edit == 'row': result['rasters'][0]['checks']['effective_resolution'] = 'indeterminate'
            if edit == 'presence':
                result['rasters'][0]['link']['presence']['status'] = 'passed'
            if edit == 'production': result['production_ready'] = True
            with self.subTest(edit=edit), self.assertRaises(ValidationError): output.validate(success_result('preflight_document_rasters', result, 1))

    def test_strict_schema_refuses_request_coercion(self):
        inputs, _ = self.validators(); inputs.validate({})
        for request in ({'minimum_dpi': True}, {'max_shapes': True}, {'max_shapes': 4097}, {'include_nonprinting': 1}, {'unknown': 1}):
            with self.subTest(request=request), self.assertRaises(ValidationError): inputs.validate(request)


if __name__ == '__main__': unittest.main()
