from __future__ import annotations
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator,ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError,ErrorCode
from corel_operator.results import success_result
from corel_operator.vector_geometry import normalize_paths,paths_equivalent
from vector_fakes import fixture,Curve,Shape,rectangle


class VectorGeometryTests(unittest.TestCase):
    def setUp(self):
        self.app,self.document,self.layer=fixture()
        self.source=Shape(self.layer,Curve.from_paths(self.app,[rectangle()]),'Source')
        self.target=Shape(self.layer,Curve.from_paths(self.app,[rectangle(1,0)]),'Target')
        self.app.original=self.source
        self.bridge=CorelBridge(); self.bridge.app=self.app; self.bridge._bind_target_document(self.document)
        self.source_ref=self.bridge.get_object_info(object_name='Source')['object']['object_reference']
        self.target_ref=self.bridge.get_object_info(object_name='Target')['object']['object_reference']
    def error(self,code,call,*args,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught: call(*args,**kwargs)
        self.assertEqual(caught.exception.code,code); self.assertNotIn('secret',str(caught.exception))
        return caught.exception
    def cubic(self):
        return {'start':{'x':0,'y':0},'closed':False,'segments':[
            {'type':'cubic','end':{'x':2,'y':0},'control1':{'x':0,'y':2},'control2':{'x':2,'y':2}}]}
    def test_creation_closes_paths_and_reads_exact_cubic_handles(self):
        closed=rectangle(5,5); closed['segments'].pop()
        result=self.bridge.create_vector_path([closed,self.cubic()],'Editable')
        self.assertEqual(result['created_count'],1)
        curve=result['objects'][0]['curve']; self.assertEqual(curve['segment_count'],5)
        self.assertEqual(curve['node_count'],6); self.assertEqual(curve['paths'][1]['segments'][0]['control1'],{'x':0,'y':2})
        self.assertTrue(result['source_preservation']['verified'])
        self.assertEqual(self.document.Unit,3); self.assertEqual(self.document.ReferencePoint,9)
    def test_native_bezier_bounds_do_not_use_control_polygon_bounds(self):
        result=self.bridge.create_vector_path([self.cubic()],'Bezier')
        self.assertAlmostEqual(result['objects'][0]['curve']['bounds_inches']['height'],1.5)
    def test_closed_cubic_handles_survive_closure_and_first_node_move(self):
        path={'start':{'x':0,'y':0},'closed':True,'segments':[
            {'type':'cubic','control1':{'x':0,'y':1},'control2':{'x':2,'y':1},'end':{'x':2,'y':0}},
            {'type':'cubic','control1':{'x':2,'y':-1},'control2':{'x':0,'y':-1},'end':{'x':0,'y':0}}]}
        result=self.bridge.create_vector_path([path],'ClosedBezier'); before=result['objects'][0]['curve']
        self.assertEqual(before['node_count'],2); self.assertEqual(before['segment_count'],2)
        after=self.bridge.edit_curve_geometry(before['fingerprint'],node_edits=[{'subpath_index':1,'node_index':1,'position':{'x':1,'y':1}}],object_name='ClosedBezier')['curve']
        self.assertEqual(after['paths'][0]['segments'][-1]['end'],{'x':1,'y':1})
        self.assertEqual(after['paths'][0]['segments'][-1]['control2'],{'x':1,'y':0})
    def test_bad_requests_fail_before_creating_owned_shapes(self):
        before=list(self.layer.Shapes.items)
        for value in ([],[{'start':{'x':True,'y':0},'closed':False,'segments':[]}],[{'start':{'x':0,'y':0},'closed':False,'segments':[{'type':'line','end':{'x':float('nan'),'y':1}}]}]):
            self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.create_vector_path,value)
        self.assertEqual(self.layer.Shapes.items,before)
    def test_display_curve_inspection_preserves_primitives(self):
        self.source.Type=1
        result=self.bridge.get_curve_geometry(object_name='Source')
        self.assertFalse(result['editable']); self.assertEqual(result['representation'],'display_curve')
        self.assertEqual(self.source.Type,1); self.assertEqual(self.layer.Shapes.Count,2)
    def test_geometry_fingerprints_detect_stale_nodes_before_edit(self):
        snapshot=self.bridge.get_curve_geometry(object_name='Source')['curve']
        self.source.curve.paths[0].nodes[0].PositionX=.1
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.edit_curve_geometry,snapshot['fingerprint'],
            node_edits=[{'subpath_index':1,'node_index':1,'position':{'x':1,'y':1}}],object_name='Source')
        self.assertEqual(self.source.curve.paths[0].nodes[0].PositionX,.1)
    def test_node_edits_translate_attached_handles_and_keep_appearance(self):
        result=self.bridge.create_vector_path([self.cubic()],'EditCurve'); reference=result['objects'][0]['object']['object_reference']
        before=result['objects'][0]['curve']
        result=self.bridge.edit_curve_geometry(before['fingerprint'],node_edits=[{'subpath_index':1,'node_index':1,'position':{'x':1,'y':1}}],object_reference=reference)
        path=result['curve']['paths'][0]
        self.assertEqual(path['start'],{'x':1,'y':1}); self.assertEqual(path['segments'][0]['control1'],{'x':1,'y':3})
        self.assertEqual(path['segments'][0]['control2'],{'x':2,'y':2})
    def test_nodes_can_retain_absolute_handles(self):
        result=self.bridge.create_vector_path([self.cubic()],'Absolute'); before=result['objects'][0]['curve']
        revised=self.bridge.edit_curve_geometry(before['fingerprint'],node_edits=[{'subpath_index':1,'node_index':1,'position':{'x':1,'y':1},'translate_handles':False}],object_name='Absolute')
        self.assertEqual(revised['curve']['paths'][0]['segments'][0]['control1'],{'x':0,'y':2})
    def test_closed_first_node_edit_updates_closing_endpoint(self):
        before=self.bridge.get_curve_geometry(object_name='Source')['curve']
        after=self.bridge.edit_curve_geometry(before['fingerprint'],node_edits=[{'subpath_index':1,'node_index':1,'position':{'x':.2,'y':.2}}],object_name='Source')['curve']
        self.assertEqual(after['paths'][0]['start'],after['paths'][0]['segments'][-1]['end'])
        self.assertEqual(after['node_count'],4)
    def test_complete_edit_preflight_rejects_invalid_indices_duplicates_and_line_handles(self):
        before=self.bridge.get_curve_geometry(object_name='Source')['curve']; original=copy.deepcopy(before)
        bad={'subpath_index':1,'node_index':100,'position':{'x':1,'y':1}}
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.edit_curve_geometry,before['fingerprint'],node_edits=[bad],object_name='Source')
        bad['node_index']=1
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.edit_curve_geometry,before['fingerprint'],node_edits=[bad,bad],object_name='Source')
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.edit_curve_geometry,before['fingerprint'],handle_edits=[{'subpath_index':1,'segment_index':1,'control1':{'x':1,'y':1}}],object_name='Source')
        self.assertEqual(self.bridge.get_curve_geometry(object_name='Source')['curve'],original)
    def test_handle_edit_and_explicit_cusp_conversion(self):
        result=self.bridge.create_vector_path([self.cubic()],'Handles')
        shape=self.bridge._find_shape(self.document,object_name='Handles'); shape.curve.paths[0].nodes[0].Type=1
        before=self.bridge.get_curve_geometry(object_name='Handles')['curve']
        result=self.bridge.edit_curve_geometry(before['fingerprint'],handle_edits=[{'subpath_index':1,'segment_index':1,'control1':{'x':1,'y':2}}],convert_edited_nodes_to_cusp=True,object_name='Handles')
        self.assertEqual(result['curve']['node_types'][0][0],0)
        self.assertEqual(result['curve']['paths'][0]['segments'][0]['control1'],{'x':1,'y':2})
    def test_smooth_constraints_fail_preflight_and_explicit_cusp_can_resolve_them(self):
        paths=[{'start':{'x':0,'y':0},'closed':False,'segments':[
            {'type':'cubic','control1':{'x':1,'y':0},'control2':{'x':1,'y':0},'end':{'x':2,'y':0}},
            {'type':'cubic','control1':{'x':3,'y':0},'control2':{'x':3,'y':0},'end':{'x':4,'y':0}}]}]
        shape=Shape(self.layer,Curve.from_paths(self.app,paths),'Smooth'); shape.curve.paths[0].nodes[1].Type=2
        before=self.bridge.get_curve_geometry(object_name='Smooth')['curve']
        edit=[{'subpath_index':1,'segment_index':2,'control1':{'x':3,'y':1}}]
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.edit_curve_geometry,before['fingerprint'],handle_edits=edit,object_name='Smooth')
        self.assertEqual(self.bridge.get_curve_geometry(object_name='Smooth')['curve'],before)
        result=self.bridge.edit_curve_geometry(before['fingerprint'],handle_edits=edit,convert_edited_nodes_to_cusp=True,object_name='Smooth')
        self.assertEqual(result['curve']['node_types'][0][1],0)
    def test_ignored_native_node_writes_quarantine_followup_mutations(self):
        before=self.bridge.get_curve_geometry(object_name='Source')['curve']; self.app.ignore_move=True
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.edit_curve_geometry(before['fingerprint'],node_edits=[{'subpath_index':1,'node_index':1,'position':{'x':1,'y':1}}],object_name='Source')
                self.assertFalse(result['ok']); self.assertEqual(server.rotate_object(20,object_name='Source')['error']['code'],'RECOVERY_REQUIRED')
        finally: dispatcher.close()
    def test_boolean_derivatives_preserve_actual_sources_and_clean_copies(self):
        for operation,expected in (('weld',(0,0,3,2)),('trim',(2,0,1,2)),('intersect',(1,0,1,2))):
            before=self.bridge._vector_source_signature(self.document,self.source)
            result=self.bridge.boolean_shapes(operation,self.source_ref,self.target_ref,'Result_'+operation)
            self.assertTrue(result['source_preservation']['verified']); self.assertEqual(result['created_count'],1)
            bounds=result['objects'][0]['curve']['bounds_inches']
            self.assertEqual(tuple(bounds[k] for k in ('x','y','width','height')),expected)
            call=self.app.calls[-1]; self.assertIsNot(call[1],self.source); self.assertIsNot(call[2],self.target)
            self.assertEqual(call[3:],(True,True)); self.assertEqual(self.bridge._vector_source_signature(self.document,self.source),before)
            self.assertTrue(all(copy not in self.layer.Shapes.items for copy in self.app.duplicates))
    def test_primitive_conversions_are_confined_to_owned_copies(self):
        self.source.Type=1; self.target.Type=2
        source_ref=self.bridge.get_object_info(object_name='Source')['object']['object_reference']
        target_ref=self.bridge.get_object_info(object_name='Target')['object']['object_reference']
        result=self.bridge.boolean_shapes('intersect',source_ref,target_ref)
        self.assertEqual((self.source.Type,self.target.Type),(1,2)); self.assertTrue(result['source_preservation']['verified'])
    def test_open_primitive_display_curve_is_refused_before_copying(self):
        self.source.Type=2; self.source.curve=Curve.from_paths(self.app,[self.cubic()])
        reference=self.bridge.get_object_info(object_name='Source')['object']['object_reference']
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.boolean_shapes,'weld',reference,self.target_ref)
        self.assertFalse(self.app.duplicates)
    def test_different_layers_and_closed_document_are_refused_before_copying(self):
        from vector_fakes import Layer
        layer=Layer(self.document.ActivePage,'Other'); self.document.ActivePage.AllLayers.items.append(layer)
        other=Shape(layer,Curve.from_paths(self.app,[rectangle()]),'Other')
        reference=self.bridge._reference_for_shape(self.document,other)
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.boolean_shapes,'weld',self.source_ref,reference)
        self.assertFalse(self.app.duplicates)
        self.app.Documents.items=[]
        self.error(ErrorCode.NO_TARGET_DOCUMENT,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
    def test_open_boolean_inputs_fail_before_native_mutation(self):
        shape=Shape(self.layer,Curve.from_paths(self.app,[self.cubic()]),'Open')
        reference=self.bridge.get_object_info(object_name='Open')['object']['object_reference']
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.boolean_shapes,'weld',reference,self.target_ref)
        self.assertFalse(self.app.duplicates); self.assertFalse(self.app.calls)
    def test_empty_intersection_is_explicit_and_leaves_no_copies(self):
        self.target.curve=Curve.from_paths(self.app,[rectangle(4,0)])
        result=self.bridge.boolean_shapes('intersect',self.source_ref,self.target_ref)
        self.assertTrue(result['empty_result']); self.assertEqual(result['created_count'],0); self.assertEqual(self.layer.Shapes.Count,2)
    def test_native_boolean_failure_cleans_owned_inputs(self):
        self.app.boolean_failure=True
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
        self.assertTrue(error.details['rollback']['verified']); self.assertEqual(self.layer.Shapes.Count,2)
    def test_reused_shape_and_shared_curve_data_never_edit_originals(self):
        for flag in ('reuse_duplicate','share_curve'):
            setattr(self.app,flag,True)
            self.error(ErrorCode.COREL_COM_ERROR,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
            self.assertEqual(self.source.Name,'Source'); self.assertEqual(self.layer.Shapes.Count,2)
            setattr(self.app,flag,False)
    def test_source_corruption_and_unknown_outputs_are_not_claimed_as_rollback(self):
        self.app.mutate_original=True
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
        self.assertFalse(error.details['rollback']['verified'])
        self.source.curve.paths[0].nodes[0].PositionX=0; self.app.mutate_original=False; self.app.extra_output=True
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
        self.assertFalse(error.details['rollback']['verified']); self.assertTrue(any(s.Name=='UnknownExtra' for s in self.layer.Shapes.items))
    def test_reordered_originals_cannot_be_claimed_as_preserved(self):
        original=Shape._boolean
        def reversed_roots(shape,*args):
            result=original(shape,*args); self.layer.Shapes.items.reverse(); return result
        with patch.object(Shape,'_boolean',reversed_roots):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
        self.assertFalse(error.details['rollback']['verified'])
    def test_curve_budget_is_enforced_before_shaping(self):
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.create_vector_path,[rectangle()]*65)
        with patch('corel_operator.vector_bridge.MAX_SEGMENTS',2):
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
        self.assertFalse(self.app.duplicates)
    def test_cleanup_failure_preserves_sources_and_requires_recovery(self):
        self.app.boolean_failure=True; self.app.fail_delete=True
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
        self.assertFalse(error.details['rollback']['verified']); self.assertIn(self.source,self.layer.Shapes.items)
    def test_combination_reconciles_reordered_native_paths(self):
        result=self.bridge.combine_vector_shapes([self.source_ref,self.target_ref],'Compound')
        self.assertEqual(result['created_count'],1); self.assertEqual(len(result['objects'][0]['curve']['paths']),2)
        self.assertTrue(paths_equivalent(result['objects'][0]['curve']['paths'],[rectangle(),rectangle(1,0)]))
        self.assertEqual(self.layer.Shapes.Count,3)
    def test_combination_rejects_lost_subpaths_and_cleans_only_owned_output(self):
        self.app.corrupt_combined=True
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.combine_vector_shapes,[self.source_ref,self.target_ref])
        self.assertTrue(error.details['rollback']['verified']); self.assertEqual(self.layer.Shapes.Count,2)
    def test_break_apart_matches_native_order_to_source_names(self):
        combined=self.bridge.combine_vector_shapes([self.source_ref,self.target_ref],'Compound')
        reference=combined['objects'][0]['object']['object_reference']
        result=self.bridge.break_apart_curve(reference,'Piece')
        self.assertEqual(result['created_count'],2)
        self.assertEqual([s['object']['object_name'] for s in result['objects']],['Piece_001','Piece_002'])
        self.assertTrue(paths_equivalent([s['curve']['paths'][0] for s in result['objects']],combined['objects'][0]['curve']['paths']))
        self.assertEqual(self.layer.Shapes.Count,5)
    def test_replaced_referenced_shape_and_repeated_input_are_refused(self):
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.combine_vector_shapes,[self.source_ref,self.source_ref])
        replacement=Shape(self.layer,self.source.curve.clone(),'Source')
        self.source.Delete()
        self.error(ErrorCode.OBJECT_NOT_FOUND,self.bridge.boolean_shapes,'weld',self.source_ref,self.target_ref)
        self.assertIn(replacement,self.layer.Shapes.items); self.assertFalse(self.app.duplicates)
    def test_new_path_factory_cannot_rename_an_existing_shape(self):
        self.app.return_existing_shape=True
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.create_vector_path,[rectangle(5,5)],'NewName')
        self.assertEqual(self.source.Name,'Source'); self.assertEqual(self.layer.Shapes.Count,2)
    def test_unknown_native_node_types_and_aliases_fail_inspection(self):
        self.source.curve.paths[0].nodes[0].Type=3
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE,self.bridge.get_curve_geometry,object_name='Source')
        self.source.curve.paths[0].nodes[0].Type=0
        self.source.curve.paths[0].segments[0].EndNode=self.source.curve.paths[0].nodes[0]
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.get_curve_geometry,object_name='Source')
    def test_closed_curve_equivalence_allows_reversal_but_not_lost_geometry(self):
        original=rectangle(); reversed_path={'start':{'x':0,'y':0},'closed':True,'segments':[
            {'type':'line','end':{'x':0,'y':2}},{'type':'line','end':{'x':2,'y':2}},
            {'type':'line','end':{'x':2,'y':0}},{'type':'line','end':{'x':0,'y':0}}]}
        self.assertTrue(paths_equivalent([original],[reversed_path]))
        reversed_path['segments'][0]['end']['y']=3
        self.assertFalse(paths_equivalent([original],[reversed_path]))
    def test_native_result_schemas_are_strict(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tools={t['name']:t for t in registry['tools']}
        inspection=self.bridge.get_curve_geometry(object_name='Source')
        values={'get_curve_geometry':inspection,'create_vector_path':self.bridge.create_vector_path([self.cubic()],'New'),
            'boolean_shapes':self.bridge.boolean_shapes('intersect',self.source_ref,self.target_ref),
            'combine_vector_shapes':self.bridge.combine_vector_shapes([self.source_ref,self.target_ref],'Compound')}
        values['break_apart_curve']=self.bridge.break_apart_curve(values['combine_vector_shapes']['objects'][0]['object']['object_reference'])
        values['edit_curve_geometry']=self.bridge.edit_curve_geometry(inspection['curve']['fingerprint'],node_edits=[{'subpath_index':1,'node_index':1,'position':{'x':.1,'y':.1}}],object_name='Source')
        for name,value in values.items():
            validator=Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tools[name]['output_schema']})
            validator.validate(success_result(name,value,1)); bad=copy.deepcopy(value); bad['unknown']=True
            with self.assertRaises(ValidationError): validator.validate(success_result(name,bad,1))


if __name__=='__main__': unittest.main()
