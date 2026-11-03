import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result
from organization_fakes import Collection, Layer, Page, add_shape, fixture


class OrganizationTests(unittest.TestCase):
    def setUp(self):
        self.bridge, self.doc = fixture()
        self.state = self.bridge.get_document_structure()['structure']
        self.front, self.back = [row['page_identity'] for row in self.state['pages']]
        self.layer = self.state['pages'][0]['layers'][0]['layer_identity']

    def fresh(self):
        return self.bridge.get_document_structure()['structure']['fingerprint']

    def error(self, code, method, *args, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            getattr(self.bridge, method)(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn('Private', str(caught.exception)); self.assertNotIn('secret', str(caught.exception))
        return caught.exception

    def test_inspection_is_deterministic_bounded_json_and_preserves_context(self):
        self.assertEqual(self.state, self.bridge.get_document_structure()['structure'])
        self.assertNotIn('python:', json.dumps(self.state)); self.assertNotIn('iunknown:', json.dumps(self.state))
        self.assertEqual(self.doc.calls, []); self.assertEqual((self.doc.Unit, self.doc.ReferencePoint), (3, 9))
        self.assertTrue(self.state['master_layers'][0]['master'])
        self.assertEqual(self.state['pages'][0]['width_inches'], 8.)

    def test_inspection_refuses_ambiguous_pages_layers_and_roots(self):
        for mutation in ('page', 'layer', 'shape'):
            bridge, doc = fixture()
            collection = doc.Pages if mutation == 'page' else doc.Pages.items[0].Layers if mutation == 'layer' else doc.ActivePage.ActiveLayer.Shapes
            collection.items.append(collection.items[0])
            with self.assertRaises(CorelBridgeError): bridge.get_document_structure()
            self.assertEqual(doc.calls, [])

    def test_inspection_refuses_unreadable_flags_dimensions_and_foreign_ownership(self):
        for mutation in ('flag', 'dimension', 'layer_owner', 'shape_owner', 'all_layers'):
            bridge, doc = fixture(); page = doc.ActivePage
            if mutation == 'flag': object.__setattr__(page.ActiveLayer, 'Visible', 1)
            if mutation == 'dimension': page.SizeWidth = float('nan')
            if mutation == 'layer_owner': page.ActiveLayer.Page = doc.Pages.items[1]
            if mutation == 'shape_owner': page.ActiveLayer.Shapes.items[0].Page = doc.Pages.items[1]
            if mutation == 'all_layers': page.Layers.items.append(Layer(doc.MasterPage, 'Foreign'))
            with self.assertRaises(CorelBridgeError): bridge.get_document_structure()
            self.assertEqual(doc.calls, [])

    def test_inspection_enforces_page_layer_and_total_budgets(self):
        for limit in ('pages', 'layers', 'items'):
            bridge, doc = fixture()
            if limit == 'pages': doc.Pages.items = [Page(doc, str(i)) for i in range(257)]; doc.ActivePage = doc.Pages.items[0]
            if limit == 'layers': doc.ActivePage.Layers.items = [Layer(doc.ActivePage, str(i)) for i in range(129)]
            if limit == 'items':
                for i in range(4097): add_shape(doc.ActivePage.ActiveLayer, str(i), i + 2000)
            with self.assertRaises(CorelBridgeError) as caught: bridge.get_document_structure()
            self.assertEqual(caught.exception.code, ErrorCode.UNSUPPORTED_IN_PROFILE)
            self.assertEqual(doc.Unit, 3)

    def test_inspection_detects_ignored_unit_entry_and_ignored_restoration(self):
        for flag in ('ignore_inch_units', 'ignore_unit_restore'):
            bridge, doc = fixture(); state = bridge.get_document_structure()['structure']; doc.flags[flag] = True
            with self.assertRaises(CorelBridgeError) as caught:
                bridge.activate_page(state['pages'][1]['page_identity'], state['fingerprint'])
            self.assertEqual(caught.exception.code, ErrorCode.COREL_COM_ERROR)
            self.assertTrue(bridge._operation_mutation_started)

    def test_stale_fingerprint_refuses_every_mutation_before_native_calls(self):
        self.doc.ActivePage.SizeWidth += .1
        cases = [('activate_page', (self.back, self.state['fingerprint'])),
            ('activate_layer', (self.front, self.layer, self.state['fingerprint'])),
            ('rename_page', (self.front, 'Cover', self.state['fingerprint'])),
            ('create_page', ('Sheet 3', 8., 10., self.state['fingerprint'])),
            ('create_layer', (self.front, 'Print', self.state['fingerprint'])),
            ('set_layer_properties', (self.front, self.layer, {'visible': False}, self.state['fingerprint']))]
        for method, args in cases: self.error(ErrorCode.INVALID_ARGUMENT, method, *args)
        self.assertEqual(self.doc.calls, [])

    def test_fingerprint_changes_with_rename_flags_order_membership_and_active_context(self):
        for kind in ('name', 'flags', 'order', 'membership', 'active', 'new_session'):
            bridge, doc = fixture(); before = bridge.get_document_structure()['structure']['fingerprint']
            if kind == 'name': object.__setattr__(doc.ActivePage, 'Name', 'Renamed')
            if kind == 'flags': object.__setattr__(doc.ActivePage.ActiveLayer, 'Visible', False)
            if kind == 'order': doc.Pages.items.reverse()
            if kind == 'membership': doc.ActivePage.ActiveLayer.Shapes.items.reverse()
            if kind == 'active': doc.ActivePage = doc.Pages.items[1]
            if kind == 'new_session': bridge._bridge_session_id = 'another-session'
            self.assertNotEqual(before, bridge.get_document_structure()['structure']['fingerprint'])

    def test_invalid_fingerprint_identity_and_names_have_no_native_calls(self):
        for value in ('', 'z' * 64, True, None): self.error(ErrorCode.INVALID_ARGUMENT, 'activate_page', self.front, value)
        self.error(ErrorCode.OBJECT_NOT_FOUND, 'activate_page', 'unknown', self.fresh())
        self.error(ErrorCode.INVALID_ARGUMENT, 'activate_page', 1, self.fresh())
        for name in ('', ' ', 'x' * 129, 'a\nb', True):
            self.error(ErrorCode.INVALID_ARGUMENT, 'rename_page', self.front, name, self.fresh())
        self.assertEqual(self.doc.calls, [])

    def test_activation_unlocks_exact_cross_page_signed_reference_editing(self):
        shape = self.doc.Pages.items[1].ActiveLayer.Shapes.items[0]
        reference = self.bridge._reference_for_shape(self.doc, shape)
        self.assertIsNotNone(reference)
        with self.assertRaises(CorelBridgeError): self.bridge._resolve_object_reference(self.doc, reference, mutation=True)
        result = self.bridge.activate_page(self.back, self.fresh())
        self.assertTrue(result['updated']); self.assertIs(self.doc.ActivePage, shape.Page)
        resolved, _ = self.bridge._resolve_object_reference(self.doc, reference, mutation=True)
        self.assertIs(resolved, shape)

    def test_activation_and_rename_noops_do_not_write_pages_or_layers(self):
        self.assertFalse(self.bridge.activate_page(self.front, self.fresh())['updated'])
        self.assertFalse(self.bridge.rename_page(self.front, 'Front', self.fresh())['updated'])
        self.assertEqual(self.doc.calls, [])
        self.assertFalse(self.bridge._operation_mutation_started)

    def test_layer_activation_routes_later_creation_and_preserves_other_structure(self):
        created = self.bridge.create_layer(self.back, 'Output', self.fresh())
        before = created['structure']; target = created['created_layer_identity']
        result = self.bridge.activate_layer(self.back, target, self.fresh())
        self.assertEqual(result['structure']['active_page_identity'], self.back)
        self.assertEqual(self.doc.ActivePage.ActiveLayer.Name, 'Output')
        expected = copy.deepcopy(before); expected['active_page_identity'] = self.back
        expected['pages'][1]['active_layer_identity'] = target
        self.assertEqual(self.bridge._organization_plain(result['structure']), self.bridge._organization_plain(expected))

    def test_layer_activation_refuses_locked_hidden_master_and_foreign_targets(self):
        for field in ('Editable', 'Visible'):
            object.__setattr__(self.doc.ActivePage.ActiveLayer, field, False)
            self.error(ErrorCode.INVALID_ARGUMENT, 'activate_layer', self.front, self.layer, self.fresh())
            object.__setattr__(self.doc.ActivePage.ActiveLayer, field, True)
        self.error(ErrorCode.OBJECT_NOT_FOUND, 'activate_layer', self.back, self.layer, self.fresh())
        self.error(ErrorCode.OBJECT_NOT_FOUND, 'activate_layer', self.front, self.state['master_layers'][0]['layer_identity'], self.fresh())
        self.assertEqual(self.doc.calls, [])

    def test_layer_activation_failure_is_detected_and_same_layer_noop_has_no_calls(self):
        self.assertFalse(self.bridge.activate_layer(self.front, self.layer, self.fresh())['updated'])
        self.assertEqual(self.doc.calls, [])
        created = self.bridge.create_layer(self.back, 'Output', self.fresh())
        self.doc.flags['ignore_layer_restore'] = True
        self.error(ErrorCode.COREL_COM_ERROR, 'activate_layer', self.back, created['created_layer_identity'], self.fresh())

    def test_activation_rejects_ignored_or_side_effected_native_changes(self):
        for flag in ('ignore_activate', 'activate_changes_layer', 'fail_activate'):
            bridge, doc = fixture(); state = bridge.get_document_structure()['structure']; doc.flags[flag] = True
            with self.assertRaises(CorelBridgeError): bridge.activate_page(state['pages'][1]['page_identity'], state['fingerprint'])
            self.assertTrue(bridge._operation_mutation_started)

    def test_rename_page_preserves_other_structure_and_rejects_duplicates(self):
        result = self.bridge.rename_page(self.back, 'Reverse', self.fresh())
        expected = copy.deepcopy(self.state); expected['pages'][1]['name'] = 'Reverse'; expected.pop('fingerprint')
        self.assertEqual(expected, self.bridge._organization_plain(result['structure']))
        self.error(ErrorCode.INVALID_ARGUMENT, 'rename_page', self.front, 'reverse', self.fresh())

    def test_rename_failure_is_redacted_and_requires_recovery(self):
        self.doc.flags['fail_page_name'] = True
        error = self.error(ErrorCode.COREL_COM_ERROR, 'rename_page', self.front, 'Cover', self.fresh())
        self.assertTrue(error.details['recovery_required']); self.assertEqual(self.doc.ActivePage.Name, 'Cover')

    def test_layer_properties_reconcile_flags_and_name_in_exact_scope(self):
        result = self.bridge.set_layer_properties(self.front, self.layer, {'name': 'Print', 'visible': False, 'printable': False, 'editable': False}, self.fresh())
        row = result['structure']['pages'][0]['layers'][0]
        self.assertEqual((row['name'], row['visible'], row['printable'], row['editable']), ('Print', False, False, False))
        self.assertEqual(row['root_shape_identities'], self.state['pages'][0]['layers'][0]['root_shape_identities'])
        self.assertEqual(result['structure']['active_page_identity'], self.front)

    def test_layer_property_noop_has_no_native_writes(self):
        result = self.bridge.set_layer_properties(self.front, self.layer, {'visible': True}, self.fresh())
        self.assertFalse(result['updated']); self.assertEqual(self.doc.calls, [])

    def test_layer_properties_reject_master_special_foreign_and_duplicate_names(self):
        self.error(ErrorCode.OBJECT_NOT_FOUND, 'set_layer_properties', self.back, self.layer, {'visible': False}, self.fresh())
        self.error(ErrorCode.OBJECT_NOT_FOUND, 'set_layer_properties', self.front, self.state['master_layers'][0]['layer_identity'], {'visible': False}, self.fresh())
        object.__setattr__(self.doc.ActivePage.ActiveLayer, 'IsSpecialLayer', True)
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE, 'set_layer_properties', self.front, self.layer, {'visible': False}, self.fresh())
        object.__setattr__(self.doc.ActivePage.ActiveLayer, 'IsSpecialLayer', False)
        self.error(ErrorCode.INVALID_ARGUMENT, 'set_layer_properties', self.front, self.layer, {'name': 'master'}, self.fresh())
        self.assertEqual(self.doc.calls, [])

    def test_layer_properties_reject_bad_fields_and_boolean_coercions(self):
        for value in ({}, {'master': True}, {'visible': 1}, {'printable': None}, {'name': '\n'}, []):
            self.error(ErrorCode.INVALID_ARGUMENT, 'set_layer_properties', self.front, self.layer, value, self.fresh())
        self.assertEqual(self.doc.calls, [])

    def test_partial_or_ignored_layer_writes_require_recovery_without_undo(self):
        for flag in ('ignore_Visible', 'fail_Printable'):
            bridge, doc = fixture(); state = bridge.get_document_structure()['structure']; doc.flags[flag] = True
            with self.assertRaises(CorelBridgeError) as caught:
                bridge.set_layer_properties(state['pages'][0]['page_identity'], state['pages'][0]['layers'][0]['layer_identity'], {'visible': False, 'printable': False}, state['fingerprint'])
            self.assertTrue(caught.exception.details['recovery_required']); self.assertTrue(bridge._operation_mutation_started)

    def test_create_page_appends_explicit_size_and_restores_existing_context(self):
        result = self.bridge.create_page('Sheet 3', 12., 18., self.fresh())
        state = result['structure']; row = state['pages'][-1]
        self.assertEqual((row['name'], row['width_inches'], row['height_inches'], row['page_index']), ('Sheet 3', 12., 18., 3))
        self.assertEqual(row['page_identity'], result['created_page_identity']); self.assertEqual(state['pages'][:-1], self.state['pages'])
        self.assertEqual(state['master_layers'], self.state['master_layers']); self.assertEqual(state['active_page_identity'], self.front)
        self.assertIn(('size', 12., 18., self.bridge.CDR_INCH), self.doc.calls); self.assertEqual(self.doc.Unit, 3)
        self.assertEqual(sum(call[0] == 'add_pages' for call in self.doc.calls), 1)

    def test_create_page_invalid_size_and_duplicate_name_are_preflighted(self):
        for width in (0., -.1, float('nan'), float('inf'), True, 2001.):
            self.error(ErrorCode.INVALID_ARGUMENT, 'create_page', 'Sheet 3', width, 18., self.fresh())
        self.error(ErrorCode.INVALID_ARGUMENT, 'create_page', 'front', 12., 18., self.fresh())
        self.assertEqual(self.doc.calls, [])

    def test_owned_empty_page_is_removed_after_ignored_size_or_name(self):
        for flag in ('ignore_size', 'ignore_page_name', 'fail_page_name'):
            bridge, doc = fixture(); state = bridge.get_document_structure()['structure']; doc.flags[flag] = True
            with self.assertRaises(CorelBridgeError) as caught: bridge.create_page('Sheet 3', 12., 18., state['fingerprint'])
            self.assertTrue(caught.exception.details['rollback']['verified']); self.assertEqual(doc.Pages.Count, 2)
            self.assertEqual(bridge.get_document_structure()['structure'], state)

    def test_unowned_populated_or_lost_page_receipts_are_never_deleted(self):
        for flag in ('existing_page_receipt', 'foreign_page_receipt', 'populated_page', 'extra_page', 'fail_add_pages', 'change_original'):
            bridge, doc = fixture(); state = bridge.get_document_structure()['structure']; doc.flags[flag] = True
            with self.assertRaises(CorelBridgeError): bridge.create_page('Sheet 3', 12., 18., state['fingerprint'])
            self.assertFalse(any(call[0] == 'page_delete' for call in doc.calls))
            self.assertEqual(sum(call[0] == 'add_pages' for call in doc.calls), 1)

    def test_cleanup_delete_failure_keeps_new_page_and_requires_recovery(self):
        self.doc.flags.update(ignore_size=True, fail_delete=True)
        error = self.error(ErrorCode.COREL_COM_ERROR, 'create_page', 'Sheet 3', 12., 18., self.fresh())
        self.assertFalse(error.details['rollback']['verified']); self.assertTrue(error.details['recovery_required'])
        self.assertEqual(self.doc.Pages.Count, 3)

    def test_command_group_close_failure_is_not_replayed_or_reported_recovered(self):
        self.doc.flags['fail_end'] = True
        error = self.error(ErrorCode.COREL_COM_ERROR, 'create_page', 'Sheet 3', 12., 18., self.fresh())
        self.assertEqual(sum(call[0] == 'end' for call in self.doc.calls), 1)
        self.assertFalse(error.details['rollback']['verified']); self.assertTrue(error.details['rollback']['command_group_close_failed'])

    def test_command_group_begin_failure_is_not_replayed_or_reported_recovered(self):
        self.doc.flags['fail_begin'] = True
        error = self.error(ErrorCode.COREL_COM_ERROR, 'create_page', 'Sheet 3', 12., 18., self.fresh())
        self.assertEqual(sum(call[0] == 'begin' for call in self.doc.calls), 1)
        self.assertFalse(any(call[0] in ('end', 'add_pages') for call in self.doc.calls))
        self.assertFalse(error.details['rollback']['verified']); self.assertTrue(error.details['rollback']['command_group_begin_failed'])

    def test_creation_reserves_bounded_capacity_before_native_calls(self):
        for method in ('create_page', 'create_layer'):
            bridge, doc = fixture()
            for i in range(4080): add_shape(doc.ActivePage.ActiveLayer, str(i), i + 2000)
            state = bridge.get_document_structure()['structure']
            if method == 'create_layer':
                # Exact local/AllLayers additions consume two scan entries.
                for i in range(3): add_shape(doc.ActivePage.ActiveLayer, 'Extra' + str(i), i + 9000)
                state = bridge.get_document_structure()['structure']
            args = ('Sheet 3', 12., 18., state['fingerprint']) if method == 'create_page' else (state['pages'][0]['page_identity'], 'Print', state['fingerprint'])
            with self.assertRaises(CorelBridgeError) as caught: getattr(bridge, method)(*args)
            self.assertEqual(caught.exception.code, ErrorCode.UNSUPPORTED_IN_PROFILE); self.assertEqual(doc.calls, [])

    def test_create_layer_on_inactive_page_restores_page_and_both_active_layers(self):
        result = self.bridge.create_layer(self.back, 'Print', self.fresh())
        self.assertEqual(result['structure']['active_page_identity'], self.front)
        self.assertEqual(result['structure']['pages'][1]['active_layer_identity'], self.state['pages'][1]['active_layer_identity'])
        self.assertEqual(result['structure']['pages'][1]['layers'][-1]['name'], 'Print')
        self.assertEqual(result['created_layer_identity'], result['structure']['pages'][1]['layers'][-1]['layer_identity'])
        self.assertEqual(result['structure']['pages'][0], self.state['pages'][0])

    def test_create_layer_duplicate_preflight_and_owned_wrong_name_cleanup(self):
        self.error(ErrorCode.INVALID_ARGUMENT, 'create_layer', self.front, 'artwork', self.fresh())
        self.error(ErrorCode.INVALID_ARGUMENT, 'create_layer', self.front, 'master', self.fresh())
        self.assertEqual(self.doc.calls, [])
        self.doc.flags['wrong_layer_name'] = True
        error = self.error(ErrorCode.COREL_COM_ERROR, 'create_layer', self.front, 'Print', self.fresh())
        self.assertTrue(error.details['rollback']['verified']); self.assertEqual(self.bridge.get_document_structure()['structure'], self.state)

    def test_create_layer_never_deletes_foreign_populated_unknown_or_lost_receipts(self):
        for flag in ('existing_layer_receipt', 'foreign_layer_receipt', 'populated_layer', 'extra_layer', 'fail_create_layer'):
            bridge, doc = fixture(); state = bridge.get_document_structure()['structure']; doc.flags[flag] = True
            with self.assertRaises(CorelBridgeError): bridge.create_layer(state['pages'][0]['page_identity'], 'Print', state['fingerprint'])
            self.assertFalse(any(call[0] == 'layer_delete' for call in doc.calls))

    def test_ignored_context_restore_cannot_pass_success_readback(self):
        self.doc.flags['ignore_layer_restore'] = True
        error = self.error(ErrorCode.COREL_COM_ERROR, 'create_layer', self.back, 'Print', self.fresh())
        self.assertEqual(self.doc.Pages.items[1].Layers.Count, 1)
        self.assertTrue(error.details['rollback']['verified'])

    def test_closed_bound_document_refuses_organization_writes(self):
        self.bridge.app.Documents.items.clear()
        self.error(ErrorCode.NO_TARGET_DOCUMENT, 'activate_page', self.back, self.state['fingerprint'])
        self.assertEqual(self.doc.calls, [])

    def test_partial_native_structure_changes_quarantine_writes_but_allow_inspection(self):
        self.doc.flags['fail_Printable'] = True
        with patch.object(server, 'CorelBridge', return_value=self.bridge): dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                result = server.set_layer_properties(self.front, self.layer, {'visible': False, 'printable': False}, self.fresh())
                self.assertFalse(result['ok']); self.assertNotIn('secret', str(result))
                self.assertEqual(server.activate_page(self.back, self.fresh())['error']['code'], 'RECOVERY_REQUIRED')
                self.assertTrue(server.get_document_structure()['ok'])
        finally: dispatcher.close()

    def test_stale_preflight_does_not_quarantine_after_verified_unit_restoration(self):
        self.doc.ActivePage.SizeWidth += .1
        with patch.object(server, 'CorelBridge', return_value=self.bridge): dispatcher = server.CorelDispatcher()
        try:
            with patch.object(server, 'dispatcher', dispatcher):
                self.assertEqual(server.activate_page(self.back, self.state['fingerprint'])['error']['code'], 'INVALID_ARGUMENT')
                self.assertTrue(server.activate_page(self.back, self.fresh())['ok'])
        finally: dispatcher.close()

    def test_server_dispatch_and_operation_record_wrappers_cover_all_tools(self):
        cases = [('get_document_structure', ()), ('activate_page', (self.back, self.fresh())),
            ('activate_layer', (self.front, self.layer, self.fresh())),
            ('rename_page', (self.front, 'Cover', self.fresh())), ('create_page', ('Sheet 3', 12., 18., self.fresh())),
            ('create_layer', (self.front, 'Print', self.fresh())),
            ('set_layer_properties', (self.front, self.layer, {'visible': False}, self.fresh()))]
        with patch.object(server, '_tool', return_value={'ok': True}) as tool:
            for name, args in cases:
                self.assertEqual(getattr(server, name)(*args), {'ok': True}); tool.assert_called_with(name, name, *args)

    def test_actual_results_match_registered_schema(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tools = {tool['name']: tool for tool in registry['tools']}; definitions = registry['schema_definitions']
        calls = [('get_document_structure', lambda: self.bridge.get_document_structure()),
            ('activate_page', lambda: self.bridge.activate_page(self.back, self.fresh())),
            ('activate_layer', lambda: self.bridge.activate_layer(self.front, self.layer, self.fresh())),
            ('rename_page', lambda: self.bridge.rename_page(self.front, 'Cover', self.fresh())),
            ('create_page', lambda: self.bridge.create_page('Sheet 3', 12., 18., self.fresh())),
            ('create_layer', lambda: self.bridge.create_layer(self.front, 'Print', self.fresh())),
            ('set_layer_properties', lambda: self.bridge.set_layer_properties(self.front, self.layer, {'visible': False}, self.fresh()))]
        for name, call in calls:
            schema = dict(tools[name]['output_schema']); schema['schema_definitions'] = definitions
            Draft202012Validator(schema).validate(success_result(name, call(), 1))


if __name__ == '__main__': unittest.main()
