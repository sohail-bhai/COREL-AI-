import copy
import json
import unittest
from unittest.mock import patch
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.print_runs import plan_print_run, validate_repeat, validate_run_plan, verify_repeat_copy, seal
from print_run_fakes import fixture, Shape, rectangle
from powerclip_fakes import Clip
from corel_operator.results import success_result


class PrintRunTests(unittest.TestCase):
    def setUp(self):
        self.bridge, self.app, self.source, self.root = fixture()
        self.repeat = self.bridge.inspect_print_repeat(object_name='Repeat')['repeat']
    def plan(self, **options):
        args = dict(copies=5, sheet_width_inches=6.5, sheet_height_inches=2.5, gutter_inches=0.)
        args.update(options)
        return plan_print_run(self.repeat, **args)
    def execute(self, **options):
        plan = self.plan(**options)
        return self.bridge.execute_print_run(plan, plan['fingerprint'])
    def test_inspection_reconciles_full_paths_and_preserves_context(self):
        self.assertEqual(self.repeat['segment_count'], 4)
        self.assertEqual(self.repeat['node_count'], 1)
        self.assertEqual(self.repeat, json.loads(json.dumps(self.repeat)))
        self.assertEqual((self.source.Unit, self.source.ReferencePoint, self.source.Dirty), (3, 9, False))
        self.assertEqual(len(self.app.outputs), 0)
        self.assertIs(self.app.ActiveDocument, self.app.Documents.Item(2))
    def test_plan_materializes_all_full_and_partial_sheets_without_overage(self):
        plan = self.plan()
        self.assertEqual([s['copy_count'] for s in plan['sheets']], [2, 2, 1])
        self.assertEqual([s['partial'] for s in plan['sheets']], [False, False, True])
        self.assertEqual([p['copy_index'] for p in plan['placements']], [1, 2, 3, 4, 5])
        self.assertEqual([p['page_index'] for p in plan['placements']], [1, 1, 2, 2, 3])
        self.assertEqual(plan['summary']['overage'], 0)
        self.assertFalse(plan['production_ready'])
        self.assertEqual(validate_run_plan(plan, plan['fingerprint']), plan)
    def test_native_execution_creates_editable_independent_output(self):
        before = self.bridge._organization_state(self.source)[0]
        result = self.execute()
        self.assertEqual((result['copy_count'], result['sheet_count'], result['output_shape_count']), (5, 3, 5))
        self.assertEqual(self.bridge._organization_state(self.source)[0], before)
        self.assertEqual(self.bridge._print_repeat_tree(self.source, self.root)[0], self.repeat['tree'])
        self.assertTrue(result['source_preservation']['verified'])
        self.assertEqual([p.ActiveLayer.Shapes.Count for p in self.bridge.target_doc.Pages.items], [2, 2, 1])
        self.assertTrue(all(item['object_reference'] is not None for item in result['items']))
        self.assertIs(self.app.ActiveDocument, self.bridge.target_doc)
    def test_rotation_and_sheet_orientation_are_executed_at_original_size(self):
        result = self.execute(copies=3, sheet_width_inches=2.5, sheet_height_inches=3.5, rotation_policy='best_fit')
        self.assertEqual(result['sheet_count'], 3)
        for page in self.bridge.target_doc.Pages.items:
            self.assertAlmostEqual(page.ActiveLayer.Shapes.Item(1).SizeWidth, 2.)
            self.assertAlmostEqual(page.ActiveLayer.Shapes.Item(1).SizeHeight, 3.)
        oriented = self.plan(sheet_width_inches=2.5, sheet_height_inches=3.5, sheet_orientation='best_fit')
        self.assertEqual(oriented['layout']['sheet_width_inches'], 3.5)
    def test_margins_gripper_and_mark_clearance_survive_plan(self):
        plan = self.plan(sheet_width_inches=10, sheet_height_inches=10, margin_left_inches=1., gripper_inches=.5, mark_clearance_inches=.2)
        self.assertGreaterEqual(plan['placements'][0]['x'], 1.2)
        self.assertEqual(plan['request']['gripper_inches'], .5)
    def test_bad_quantities_no_fit_and_changed_manifest_are_refused(self):
        for quantity in (0, 501, True, 1.5):
            with self.assertRaises(CorelBridgeError): self.plan(copies=quantity)
        with self.assertRaises(CorelBridgeError): self.plan(sheet_width_inches=1.)
        damaged = copy.deepcopy(self.repeat); damaged['tree']['curve']['paths'][0]['start']['x'] += 1.
        with self.assertRaises(CorelBridgeError): plan_print_run(damaged, 1, 6.5, 2.5)
        damaged = copy.deepcopy(self.repeat); damaged.pop('fingerprint'); damaged['segment_count'] = 3
        with self.assertRaises(CorelBridgeError): validate_repeat(seal(damaged))
    def test_cycles_and_deep_trees_are_bounded(self):
        damaged = copy.deepcopy(self.repeat); damaged['tree']['group_children'].append(damaged['tree'])
        with self.assertRaises(CorelBridgeError): validate_repeat(damaged)
    def test_tampered_plan_and_stale_source_fail_before_output_creation(self):
        plan = self.plan(); plan['placements'][0]['x'] += 1.
        with self.assertRaises(CorelBridgeError): self.bridge.execute_print_run(plan, plan['fingerprint'])
        plan = self.plan(); self.root.SetPosition(2., 2.)
        with self.assertRaises(CorelBridgeError): self.bridge.execute_print_run(plan, plan['fingerprint'])
        self.assertEqual(self.app.outputs, [])
    def test_native_paste_failure_discards_only_owned_output_and_restores_focus(self):
        other = self.app.ActiveDocument; self.app.fail_paste = True
        with self.assertRaises(CorelBridgeError) as caught: self.execute()
        self.assertTrue(caught.exception.details['rollback']['verified'])
        self.assertTrue(self.app.outputs[0].closed); self.assertFalse(self.source.closed)
        self.assertIs(self.app.ActiveDocument, other)
    def test_existing_document_receipt_is_never_discarded(self):
        self.app.return_existing = True
        with self.assertRaises(CorelBridgeError) as caught: self.execute()
        self.assertFalse(caught.exception.details['rollback']['output_closed'])
        self.assertFalse(self.source.closed)
    def test_foreign_document_receipt_is_never_discarded(self):
        from print_run_fakes import Document
        foreign = Document(self.app, 'Foreign app document', owned=False)
        self.app.CreateDocument = lambda: foreign
        with self.assertRaises(CorelBridgeError) as caught: self.execute()
        self.assertFalse(caught.exception.details['rollback']['output_closed'])
        self.assertFalse(foreign.closed)
    def test_shared_duplicate_wrong_placement_and_late_corruption_fail_closed(self):
        for flag in ('reuse_duplicate', 'ignore_fit', 'corrupt_prior'):
            with self.subTest(flag=flag):
                self.setUp(); setattr(self.app, flag, True)
                with self.assertRaises(CorelBridgeError) as caught: self.execute()
                self.assertTrue(caught.exception.details['rollback']['verified'])
    def test_ignored_rotation_and_failed_cleanup_are_reported(self):
        self.app.ignore_rotate = self.app.fail_close = True
        with self.assertRaises(CorelBridgeError) as caught:
            self.execute(copies=1, sheet_width_inches=2.5, sheet_height_inches=3.5, rotation_policy='best_fit')
        self.assertFalse(caught.exception.details['rollback']['verified'])
        self.assertFalse(self.source.closed)
    def test_nested_groups_keep_component_paths_and_counts(self):
        self.root.Type = 7
        child = Shape(self.root.Layer, [rectangle(1, 2, 3, 2)], 'Child')
        self.root.attach_group(child)
        self.repeat = self.bridge.inspect_print_repeat(object_name='Repeat')['repeat']
        self.assertEqual(self.execute()['output_shape_count'], 10)
    def test_locked_powerclip_keeps_payload_counts_and_unlocked_clip_is_refused(self):
        child = Shape(self.root.Layer, [rectangle(1, 2, 3, 2)], 'Clipped child')
        self.root.PowerClip = Clip(self.root); self.root.PowerClip.attach(child)
        self.root.PowerClip.ContentsLocked = False
        with self.assertRaises(CorelBridgeError): self.bridge.inspect_print_repeat(object_name='Repeat')
        self.root.PowerClip.ContentsLocked = True
        self.repeat = self.bridge.inspect_print_repeat(object_name='Repeat')['repeat']
        self.assertEqual(self.execute()['output_shape_count'], 10)
    def test_bitmap_and_unlinked_text_payload_are_preserved_in_independent_copies(self):
        for code in (5, 6):
            with self.subTest(code=code):
                self.setUp(); self.root.Type = code
                self.repeat = self.bridge.inspect_print_repeat(object_name='Repeat')['repeat']
                result = self.execute(copies=2)
                self.assertEqual(result['copy_count'], 2)
                self.assertEqual(self.bridge.target_doc.ActivePage.ActiveLayer.Shapes.Item(1).Type, code)
    def test_source_dirty_or_selection_changes_cannot_be_hidden_by_cleanup(self):
        for field in ('Dirty', 'SelectionRange'):
            with self.subTest(field=field):
                self.setUp(); original = self.root.Copy
                def copying():
                    original()
                    setattr(self.source, field, True if field == 'Dirty' else type(self.source.SelectionRange)(self.root))
                self.root.Copy = copying
                with self.assertRaises(CorelBridgeError) as caught: self.execute()
                self.assertFalse(caught.exception.details['rollback']['verified'])
                self.assertTrue(caught.exception.details['rollback']['output_closed'])
    def test_extra_output_artwork_and_late_sheet_size_change_are_detected(self):
        for kind in ('extra', 'resize'):
            with self.subTest(kind=kind):
                self.setUp(); original = self.app.CreateDocument
                def create():
                    output = original(); add = output.AddPagesEx
                    def pages(*args):
                        if kind == 'extra': Shape(output.Pages.Item(1).Layers.Item(1), name='Unplanned')
                        else: output.Pages.Item(1).SizeWidth += 1.
                        add(*args)
                    output.AddPagesEx = pages
                    return output
                self.app.CreateDocument = create
                with self.assertRaises(CorelBridgeError) as caught: self.execute()
                self.assertTrue(caught.exception.details['rollback']['verified'])
    def test_long_runs_check_all_items_and_bound_returned_references(self):
        result = self.execute(copies=101, sheet_width_inches=200., sheet_height_inches=200.)
        self.assertEqual(result['copy_count'], 101)
        self.assertEqual(len(result['items']), 100)
        self.assertTrue(result['items_truncated'])
    def test_rotation_and_nested_result_schemas_reject_missing_or_extra_evidence(self):
        registry = json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        def validator(name):
            tool = next(tool for tool in registry['tools'] if tool['name'] == name)
            return Draft202012Validator({**tool['output_schema'], 'schema_definitions': registry['schema_definitions']})
        plan = self.plan(rotation_policy='best_fit')
        validator('plan_print_run').validate(success_result('plan_print_run', plan, 1))
        bad = copy.deepcopy(plan); bad['placements'][0]['rotation_degrees'] = 45
        with self.assertRaises(ValidationError): validator('plan_print_run').validate(success_result('plan_print_run', bad, 1))
        self.root.Type = 7; self.root.attach_group(Shape(self.root.Layer, [rectangle(1, 2, 3, 2)], 'Child'))
        inspected = self.bridge.inspect_print_repeat(object_name='Repeat')
        validator('inspect_print_repeat').validate(success_result('inspect_print_repeat', inspected, 1))
        bad = copy.deepcopy(inspected); bad['repeat']['tree']['group_children'][0]['gradient']['extra'] = True
        with self.assertRaises(ValidationError): validator('inspect_print_repeat').validate(success_result('inspect_print_repeat', bad, 1))
    def test_live_effects_are_refused_during_inspection(self):
        self.root.Effects.items.append(object())
        with self.assertRaises(CorelBridgeError) as caught: self.bridge.inspect_print_repeat(object_name='Repeat')
        self.assertEqual(caught.exception.code, ErrorCode.UNSUPPORTED_IN_PROFILE)
    def test_root_transform_cannot_pass_using_unchanged_matrix(self):
        source = self.repeat['tree']; actual = copy.deepcopy(source)
        actual['transform']['bounds_inches']['x'] += 1.
        with self.assertRaises(CorelBridgeError): verify_repeat_copy(source, actual, [1., 0., 0., 1., 1., 0.])
    def test_server_planner_never_dispatches_native_work(self):
        with patch.object(server, '_tool', side_effect=AssertionError('Planner must be local')):
            result = server.plan_print_run(self.repeat, 5, 6.5, 2.5, gutter_inches=0.)
        self.assertTrue(result['ok'])
        with patch.object(server, '_tool', return_value={'ok': False}) as call:
            server.inspect_print_repeat(object_name='Repeat')
        self.assertEqual(call.call_args.args, ('inspect_print_repeat', 'inspect_print_repeat', 'Repeat', 0, None))
