from __future__ import annotations

import copy
import json
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.object_references import MAX_REFERENCE_DEPTH
from corel_operator.results import success_result
from fake_documents import attach_open_document


class Collection:
    def __init__(self, *items):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]


class Shape:
    def __init__(self, name, static_id, children=None):
        self.Name, self.StaticID = name, static_id
        self.Type = 7 if children is not None else 6
        self.Shapes = Collection(*(children or []))
        self.Text = SimpleNamespace(Story=SimpleNamespace(Text='Original', Font='Arial', Size=12))
        self.PositionX, self.PositionY, self.SizeWidth, self.SizeHeight = 1., 2., 3., 4.
        self.writes = []
        self.Fill = SimpleNamespace(Type=1, ApplyUniformFill=lambda color: self.writes.append(('fill', color)))
        self.Outline = SimpleNamespace(SetNoOutline=lambda: self.writes.append(('outline', 0)))

    def SetPosition(self, x, y):
        self.writes.append(('position', x, y))
        self.PositionX, self.PositionY = x, y

    def Duplicate(self, x, y):
        duplicate = Shape(self.Name, self.StaticID + 1000)
        duplicate.Page, duplicate.Layer = self.Page, self.Layer
        self.Layer.Shapes.items.append(duplicate)
        self.Page.Shapes.items.append(duplicate)
        return duplicate


def layer(name, *shapes):
    return SimpleNamespace(Name=name, Shapes=Collection(*shapes))


def page(*layers):
    result = SimpleNamespace(AllLayers=Collection(*layers), Shapes=Collection())
    for current_layer in layers:
        result.Shapes.items.extend(current_layer.Shapes.items)
        def assign(shape):
            shape.Page, shape.Layer = result, current_layer
            for child in shape.Shapes.items:
                assign(child)
        for shape in current_layer.Shapes.items:
            assign(shape)
    return result


class ObjectReferenceTests(unittest.TestCase):
    def setUp(self):
        self.first = Shape('TITLE', 101)
        self.nested = Shape('TITLE', 103)
        self.group = Shape('Group', 102, [self.nested])
        self.artwork = layer('Artwork', self.first, self.group)
        self.same_name_layer = layer('Artwork', Shape('TITLE', 104))
        self.front = page(self.artwork, self.same_name_layer)
        self.back_shape = Shape('TITLE', 201)
        self.back = page(layer('Artwork', self.back_shape))
        self.front.Index, self.back.Index = 1, 2
        self.document = SimpleNamespace(
            Name='Target.cdr', Pages=Collection(self.front, self.back),
            ActivePage=self.front, Unit=3, ReferencePoint=9, Dirty=False,
        )
        self.bridge = CorelBridge()
        self.bridge.app = SimpleNamespace(CreateRGBColor=lambda *rgb: rgb)
        attach_open_document(self.bridge, self.document)
        self.references = {m['static_id']: m['object_reference'] for m in self.bridge.find_objects()['matches']}

    def assert_error(self, code, method='get_text_properties', reference=None, **kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            getattr(self.bridge, method)(object_reference=reference or self.references[103], **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn('secret', str(caught.exception))
        self.assertNotIn('private', str(caught.exception))

    def test_search_references_are_json_serializable_deterministic_and_scope_distinct(self):
        encoded = json.dumps(self.references)
        self.assertNotIn('python:', encoded)
        self.assertNotIn('iunknown:', encoded)
        self.assertEqual(self.references, {m['static_id']: m['object_reference'] for m in self.bridge.find_objects()['matches']})
        self.assertEqual(len({r['shape_identity'] for r in self.references.values()}), 5)
        for reference in self.references.values():
            self.assertIsNotNone(reference)

    def test_duplicate_names_in_groups_layers_and_pages_resolve_independently(self):
        for static_id in (101, 103, 104, 201):
            result = self.bridge.get_text_properties(object_reference=self.references[static_id])
            self.assertEqual(result['object']['static_id'], static_id)

    def test_reorder_shapes_and_groups_refreshes_path_without_switching_target(self):
        self.artwork.Shapes.items.reverse()
        self.front.Shapes.items.reverse()
        self.group.Shapes.items.insert(0, Shape('TITLE', 110))
        result = self.bridge.get_text_properties(object_reference=self.references[103])
        self.assertEqual(result['object']['static_id'], 103)
        self.assertEqual(result['object']['object_reference']['shape_path'], [1, 2])

    def test_reorder_pages_and_layers_preserves_identity_and_refreshes_indices(self):
        self.document.Pages.items.reverse()
        self.front.AllLayers.items.reverse()
        result = self.bridge.get_text_properties(object_reference=self.references[103])
        refreshed = result['object']['object_reference']
        self.assertEqual((refreshed['page_index'], refreshed['layer_index']), (2, 2))
        self.assertEqual(refreshed['shape_identity'], self.references[103]['shape_identity'])

    def test_cross_page_inspection_never_activates_page_or_changes_context(self):
        before = (self.document.ActivePage, self.document.Unit, self.document.ReferencePoint, self.document.Dirty)
        reference = self.references[201]
        for method in ('get_object_info', 'get_object_bounds', 'get_text_properties', 'get_fill'):
            result = getattr(self.bridge, method)(object_reference=reference)
            self.assertEqual(result['object']['static_id'], 201)
            self.assertIsNone(result['object']['shape_index'])
        self.assertEqual(before, (self.document.ActivePage, self.document.Unit, self.document.ReferencePoint, self.document.Dirty))

    def test_cross_page_edit_is_refused_before_writing(self):
        self.assert_error(ErrorCode.INVALID_ARGUMENT, 'move_object', self.references[201], x_inches=8, y_inches=9)
        self.assertEqual(self.back_shape.writes, [])
        self.document.ActivePage = self.back
        self.bridge.move_object(8, 9, object_reference=self.references[201])
        self.assertEqual(self.back_shape.writes, [('position', 8., 9.)])

    def test_all_common_edits_reach_exact_nested_object(self):
        reference = self.references[103]
        self.bridge.set_fill_color(1, 2, 3, object_reference=reference)
        self.bridge.set_outline(0, 0, 0, width_points=0, object_reference=reference)
        self.bridge.move_object(5, 6, object_reference=reference)
        self.bridge.resize_object(7, 8, object_reference=reference)
        self.bridge.set_text_content('Changed', object_reference=reference)
        self.assertEqual(self.first.writes, [])
        self.assertEqual(self.first.Text.Story.Text, 'Original')
        self.assertEqual(self.nested.Text.Story.Text, 'Changed')
        self.assertEqual((self.nested.SizeWidth, self.nested.SizeHeight), (7., 8.))
        self.assertEqual(len(self.nested.writes), 3)

    def test_rename_returns_fresh_reference_and_retires_old_name_identity(self):
        result = self.bridge.rename_object('New title', object_reference=self.references[103])
        fresh = result['object']['object_reference']
        self.assertIsNotNone(fresh)
        self.assertEqual(self.bridge.get_text_properties(object_reference=fresh)['object']['object_name'], 'New title')
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND)

    def test_duplicate_returns_reference_to_new_object_while_source_stays_valid(self):
        result = self.bridge.duplicate_object(object_reference=self.references[101], new_name='COPY')
        fresh = result['object']['object_reference']
        self.assertNotEqual(fresh['shape_identity'], self.references[101]['shape_identity'])
        self.assertEqual(self.bridge.get_text_properties(object_reference=fresh)['object']['object_name'], 'COPY')
        self.assertEqual(self.bridge.get_text_properties(object_reference=self.references[101])['object']['static_id'], 101)

    def test_delete_does_not_fall_back_to_duplicate_name(self):
        self.group.Shapes.items.clear()
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND)
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND, 'set_text_content', new_text='Must not write')
        self.assertEqual(self.first.Text.Story.Text, 'Original')

    def test_replacement_with_same_static_id_name_and_type_is_refused(self):
        self.group.Shapes.items[0] = Shape('TITLE', 103)
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND)

    def test_changed_static_id_name_or_type_is_stale(self):
        for field, value in (('StaticID', 999), ('Name', 'Renamed'), ('Type', 1)):
            old = getattr(self.nested, field)
            setattr(self.nested, field, value)
            self.assert_error(ErrorCode.OBJECT_NOT_FOUND)
            setattr(self.nested, field, old)

    def test_move_to_another_group_layer_or_page_requires_new_reference(self):
        self.group.Shapes.items.clear()
        for destination in (self.artwork.Shapes, self.same_name_layer.Shapes, self.back.AllLayers.items[0].Shapes):
            destination.items.append(self.nested)
            self.assert_error(ErrorCode.OBJECT_NOT_FOUND)
            destination.items.pop()

    def test_replaced_parent_group_retires_old_ancestry(self):
        self.artwork.Shapes.items[1] = Shape('Group', 102, [self.nested])
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND)

    def test_duplicate_static_ids_or_identity_aliases_are_ambiguous(self):
        self.artwork.Shapes.items.append(Shape('Different', 103))
        self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR)
        self.artwork.Shapes.items[-1] = self.nested
        self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR)

    def test_ambiguous_page_and_layer_aliases_are_refused(self):
        self.document.Pages.items.append(self.front)
        self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR)
        self.document.Pages.items.pop()
        self.front.AllLayers.items.append(self.artwork)
        self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR)

    def test_deleted_or_replaced_page_and_layer_are_stale(self):
        original = self.document.Pages.items[0]
        self.document.Pages.items[0] = page(layer('Artwork'))
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND)
        self.document.Pages.items[0] = original
        self.front.AllLayers.items[0] = layer('Artwork')
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND)

    def test_bridge_restart_rejects_even_matching_document_session_numbers(self):
        bridge = CorelBridge()
        bridge.app = self.bridge.app
        attach_open_document(bridge, self.document)
        self.assertEqual(bridge._document_session_id(self.document), self.references[103]['document_session_id'])
        with self.assertRaises(CorelBridgeError) as caught:
            bridge.move_object(8, 9, object_reference=self.references[103])
        self.assertEqual(caught.exception.code, ErrorCode.OBJECT_NOT_FOUND)
        self.assertEqual(self.nested.writes, [])

    def test_reopen_or_bind_other_document_rejects_previous_document_session(self):
        self.bridge._bind_target_document(self.document, new_document=True)
        self.assert_error(ErrorCode.OBJECT_NOT_FOUND)

    def test_closed_document_clears_binding_and_never_edits_other_active_document(self):
        other = SimpleNamespace(Name='Other.cdr')
        self.bridge.app.Documents.items[:] = [other]
        self.bridge.app.ActiveDocument = other
        self.assert_error(ErrorCode.NO_TARGET_DOCUMENT, 'move_object', x_inches=8, y_inches=9)
        self.assertIsNone(self.bridge.target_doc)
        self.assertEqual(self.nested.writes, [])

    def test_tampered_reference_or_conflicting_selectors_fail_before_document_access(self):
        tampered = copy.deepcopy(self.references[103])
        tampered['object_name'] = 'TITLE modified'
        with patch.object(self.bridge, '_target_document', side_effect=AssertionError('must not access')):
            self.assert_error(ErrorCode.INVALID_ARGUMENT, reference=tampered)
            self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR, object_name='TITLE')
            self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR, shape_index=1)

    def test_malformed_references_fail_before_document_access(self):
        invalid = [[], {}, 'doc-0001:shape:103']
        for field, value in (('version', True), ('static_id', None), ('shape_identity', 'bad'), ('object_name', 'x'*257), ('shape_path', [False, 1]), ('ancestor_identities', ['a'*64]*33)):
            candidate = copy.deepcopy(self.references[103]); candidate[field] = value
            invalid.append(candidate)
        with patch.object(self.bridge, '_target_document', side_effect=AssertionError('must not access')):
            for candidate in invalid:
                with self.subTest(candidate=type(candidate).__name__):
                    with self.assertRaises(CorelBridgeError) as caught:
                        self.bridge.get_fill(object_reference=candidate)
                    self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    def test_missing_static_id_or_long_name_has_no_fabricated_reference(self):
        self.nested.Name = 'x'*257
        self.first.StaticID = None
        matches = self.bridge.find_objects()['matches']
        self.assertIsNone(next(m for m in matches if m['static_id'] == 103)['object_reference'])
        self.assertIsNone(next(m for m in matches if m['static_id'] is None)['object_reference'])

    def test_complete_scope_scan_required_even_if_target_found_first(self):
        with patch('corel_operator.corel_bridge.MAX_REFERENCE_SCAN', 5):
            self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR, reference=self.references[101])
        self.assertEqual(self.first.writes, [])

    def test_group_cycle_and_depth_limits_refuse_even_an_earlier_match(self):
        self.group.Shapes.items.append(self.group)
        self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR, reference=self.references[101])
        self.group.Shapes.items.pop()
        deep = Shape('Bottom', 500)
        for i in range(MAX_REFERENCE_DEPTH + 2):
            deep = Shape('Group', 501+i, [deep])
        self.artwork.Shapes.items.append(deep)
        self.assert_error(ErrorCode.AMBIGUOUS_SELECTOR, reference=self.references[101])

    def test_unreadable_scope_never_returns_partial_success_or_raw_com_details(self):
        class Broken:
            @property
            def StaticID(self):
                raise RuntimeError('private client token=secret')
        self.artwork.Shapes.items.append(Broken())
        self.assert_error(ErrorCode.COREL_COM_ERROR, 'move_object', self.references[101], x_inches=8, y_inches=9)
        self.assertEqual(self.first.writes, [])

    def test_legacy_inspection_issues_reference_and_index_uses_identity(self):
        result = self.bridge.get_object_info(shape_index=1)
        self.assertEqual(result['object']['object_reference'], self.references[101])
        self.assertEqual(self.bridge._index_for_shape(self.document, self.back_shape), None)
        self.assertEqual(self.bridge._index_for_shape(self.document, self.same_name_layer.Shapes.items[0]), 3)

    def test_master_layer_reference_is_scoped_to_its_recorded_page(self):
        self.back.AllLayers.items.append(self.same_name_layer)
        matches = [m for m in self.bridge.find_objects()['matches'] if m['static_id'] == 104]
        self.assertEqual(len(matches), 2)
        self.assertNotEqual(matches[0]['object_reference']['page_identity'], matches[1]['object_reference']['page_identity'])
        inspected = self.bridge.get_text_properties(object_reference=matches[1]['object_reference'])
        self.assertIsNone(inspected['object']['shape_index'])
        self.assertEqual(inspected['object']['page_index'], 2)
        self.assert_error(ErrorCode.INVALID_ARGUMENT, 'move_object', matches[1]['object_reference'], x_inches=8, y_inches=9)

    def test_native_wrapper_replacement_with_same_iunknown_preserves_identity(self):
        def ole(key):
            return SimpleNamespace(GetIUnknown=lambda: key)
        self.nested._oleobj_ = ole(10300)
        reference = next(m for m in self.bridge.find_objects()['matches'] if m['static_id'] == 103)['object_reference']
        alias = Shape('TITLE', 103); alias._oleobj_ = ole(10300)
        self.group.Shapes.items[0] = alias
        result = self.bridge.get_text_properties(object_reference=reference)
        self.assertEqual(result['object']['static_id'], 103)

    def test_reference_round_trip_and_failures_through_real_dispatcher_worker(self):
        calling_thread = threading.get_ident()
        worker_threads = []
        def make_bridge():
            bridge = CorelBridge(); bridge.app = self.bridge.app
            attach_open_document(bridge, self.document)
            worker_threads.append(threading.get_ident())
            return bridge
        with patch.object(server, 'CorelBridge', side_effect=make_bridge):
            dispatcher = server.CorelDispatcher()
            try:
                reference = dispatcher.call('find_objects')['matches'][2]['object_reference']
                result = dispatcher.call('get_text_properties', object_reference=json.loads(json.dumps(reference)))
                self.assertEqual(result['object']['static_id'], 103)
                dispatcher.call('set_text_content', 'Worker edit', object_reference=reference)
                self.group.Shapes.items.clear()
                with self.assertRaises(CorelBridgeError) as caught:
                    dispatcher.call('set_text_content', 'Forbidden', object_reference=reference)
                self.assertEqual(caught.exception.code, ErrorCode.OBJECT_NOT_FOUND)
            finally:
                dispatcher.close()
        self.assertNotEqual(worker_threads, [calling_thread])
        self.assertEqual(self.nested.Text.Story.Text, 'Worker edit')

    def test_registry_accepts_reference_round_trip_and_rejects_conflicts(self):
        registry = json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        for name in ('get_object_info','get_object_bounds','get_text_properties','get_fill','move_object'):
            tool = next(t for t in registry['tools'] if t['name'] == name)
            validator = Draft202012Validator({'schema_definitions':registry['schema_definitions'],'allOf':[tool['input_schema']]})
            request = {'object_reference':self.references[103]}
            if name == 'move_object':request.update(x_inches=5,y_inches=6)
            validator.validate(request)
            with self.assertRaises(ValidationError):validator.validate({**request,'shape_index':1})
            with self.assertRaises(ValidationError):validator.validate({**request,'object_name':'TITLE'})
            output = Draft202012Validator({'schema_definitions':registry['schema_definitions'],'allOf':[tool['output_schema']]})
            output.validate(success_result(name, getattr(self.bridge,name)(**request), 0.1))


if __name__ == '__main__':
    unittest.main()
