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
from corel_operator.vector_topology import plan_curve_topology
from vector_fakes import fixture,Curve,Shape,rectangle


def cubic():
    return {'start':{'x':0,'y':0},'closed':False,'segments':[
        {'type':'cubic','end':{'x':4,'y':0},'control1':{'x':0,'y':4},'control2':{'x':4,'y':4}}]}


def evaluate(start,segment,t):
    if segment['type']=='line': return [(1-t)*start[k]+t*segment['end'][k] for k in ('x','y')]
    return [(1-t)**3*start[k]+3*t*(1-t)**2*segment['control1'][k]+3*t*t*(1-t)*segment['control2'][k]+t**3*segment['end'][k] for k in ('x','y')]


class VectorTopologyTests(unittest.TestCase):
    def setUp(self):
        self.app,self.document,self.layer=fixture()
        self.source=Shape(self.layer,Curve.from_paths(self.app,[rectangle(),cubic()]),'TopologySource')
        self.app.original=self.source
        self.bridge=CorelBridge(); self.bridge.app=self.app; self.bridge._bind_target_document(self.document)
        self.reference=self.bridge.get_object_info(object_name='TopologySource')['object']['object_reference']
        self.before=self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
    def insertion(self,p=2,s=1,t=.5): return {'subpath_index':p,'segment_index':s,'t':t}
    def deletion(self,n=2,replacement=None):
        return {'subpath_index':1,'node_index':n,'replacement':replacement or {'type':'line'}}
    def revise(self,insertions=None,deletions=None,**kwargs):
        return self.bridge.revise_curve_topology(self.reference,self.before['fingerprint'],insertions,deletions,**kwargs)
    def error(self,call,*args,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught: call(*args,**kwargs)
        return caught.exception
    def test_cubic_subdivision_preserves_the_entire_original_locus(self):
        times=[.1,.37,.82]
        planned=plan_curve_topology(self.before,[self.insertion(t=t) for t in reversed(times)])
        path=planned['paths'][1]; boundaries=[0]+times+[1]; starts=[path['start']]+[s['end'] for s in path['segments'][:-1]]
        for i,segment in enumerate(path['segments']):
            for j in range(41):
                u=j/40; original_t=boundaries[i]+u*(boundaries[i+1]-boundaries[i])
                expected=evaluate(cubic()['start'],cubic()['segments'][0],original_t)
                actual=evaluate(starts[i],segment,u)
                for a,b in zip(actual,expected): self.assertAlmostEqual(a,b,places=11)
        self.assertFalse(planned['geometry_changed']); self.assertEqual(planned['inserted_count'],3)
    def test_midpoint_has_known_cartesian_controls_and_no_source_mutation(self):
        source=copy.deepcopy(self.before)
        result=plan_curve_topology(self.before,[self.insertion()]); path=result['paths'][1]
        self.assertEqual(path['segments'][0],{'type':'cubic','control1':{'x':0.,'y':2.},'control2':{'x':1.,'y':3.},'end':{'x':2.,'y':3.}})
        self.assertEqual(path['segments'][1]['control1'],{'x':3.,'y':3.})
        self.assertEqual(self.before,source)
    def test_straight_splits_and_source_to_output_node_mapping(self):
        planned=plan_curve_topology(self.before,[self.insertion(1,4,.75),self.insertion(1,1,.25)])
        self.assertEqual(planned['paths'][0]['segments'][0]['end'],{'x':.5,'y':0.})
        inserted=planned['inserted_nodes']; self.assertEqual([e['result_node_index'] for e in inserted],[2,6])
        mapping=[e for e in planned['retained_node_map'] if e['subpath_index']==1]
        self.assertEqual([e['result_node_index'] for e in mapping],[1,3,4,5])
        self.assertEqual(planned['node_count'],8); self.assertEqual(planned['segment_count'],7)
    def test_explicit_line_deletion_reconnects_retained_neighbours(self):
        planned=plan_curve_topology(self.before,deletions=[self.deletion()])
        self.assertEqual(planned['paths'][0]['segments'][0],{'type':'line','end':{'x':2.,'y':2.}})
        self.assertEqual(planned['deleted_nodes'],[{'subpath_index':1,'node_index':2}]); self.assertTrue(planned['geometry_changed'])
        self.assertEqual(planned['node_count'],5)
    def test_deleted_closed_start_rotates_traversal_without_reversing_winding(self):
        planned=plan_curve_topology(self.before,deletions=[self.deletion(1)])
        path=planned['paths'][0]; self.assertEqual(path['start'],{'x':2.,'y':0.})
        self.assertEqual(path['segments'][-1],{'type':'line','end':path['start']})
        self.assertEqual([e['node_index'] for e in planned['retained_node_map'] if e['subpath_index']==1],[2,3,4])
    def test_cubic_reconnection_uses_explicit_controls(self):
        replacement={'type':'cubic','control1':{'x':0,'y':1},'control2':{'x':1,'y':2}}
        planned=plan_curve_topology(self.before,deletions=[self.deletion(replacement=replacement)])
        self.assertEqual(planned['paths'][0]['segments'][0],{**replacement,'end':{'x':2.,'y':2.}})
    def test_two_node_closed_cubic_loops_support_subdivision(self):
        path={'start':{'x':0,'y':0},'closed':True,'segments':[
            {'type':'cubic','control1':{'x':0,'y':1},'control2':{'x':2,'y':1},'end':{'x':2,'y':0}},
            {'type':'cubic','control1':{'x':2,'y':-1},'control2':{'x':0,'y':-1},'end':{'x':0,'y':0}}]}
        planned=plan_curve_topology({'paths':[path]},[self.insertion(1,2)])
        self.assertEqual(planned['node_count'],3)
        self.assertEqual(planned['paths'][0]['segments'][-1]['end'],path['start'])
        self.assertEqual(planned['inserted_nodes'][0]['result_node_index'],3)
        self.assertEqual(self.error(plan_curve_topology,{'paths':[path]},deletions=[self.deletion(1)]).code,ErrorCode.INVALID_ARGUMENT)
    def test_invalid_edit_sets_fail_before_any_native_copy(self):
        bad=[({},{}),([],[]),([{'subpath_index':True,'segment_index':1,'t':.5}],None),
             ([self.insertion(t=True)],None),([self.insertion(t=0)],None),([self.insertion(t=1)],None),
             ([self.insertion(t=float('nan'))],None),([self.insertion(),self.insertion()],None),
             ([{**self.insertion(),'position':{'x':0,'y':0}}],None),
             (None,[self.deletion(replacement={'type':'line','end':{'x':1,'y':1}})]),
             (None,[self.deletion(2),self.deletion(2)]),(None,[self.deletion(2),self.deletion(3)]),
             ([self.insertion(1,1)], [self.deletion(2)]),([self.insertion(1,2)],[self.deletion(2)])]
        baseline=list(self.layer.Shapes.items)
        for insertions,deletions in bad:
            self.assertEqual(self.error(self.revise,insertions,deletions).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.layer.Shapes.items,baseline); self.assertEqual(self.app.duplicates,[])
    def test_open_endpoint_removal_and_small_closed_output_are_explicitly_refused(self):
        deletion={'subpath_index':2,'node_index':1,'replacement':{'type':'line'}}
        self.assertEqual(self.error(self.revise,deletions=[deletion]).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.error(self.revise,deletions=[self.deletion(1),self.deletion(3)]).code,ErrorCode.INVALID_ARGUMENT)
    def test_too_close_and_excessive_insertions_are_refused_before_copy(self):
        entries=[self.insertion(1,1,.5),self.insertion(1,1,.50000001)]
        self.assertEqual(self.error(self.revise,entries).code,ErrorCode.INVALID_ARGUMENT)
        entries=[self.insertion(t=(i+1)/202) for i in range(201)]
        self.assertEqual(self.error(self.revise,entries).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_total_segment_budget_is_checked_in_the_complete_plan(self):
        path={'start':{'x':0,'y':0},'closed':False,'segments':[{'type':'line','end':{'x':i+1,'y':0}} for i in range(1000)]}
        self.assertEqual(self.error(plan_curve_topology,{'paths':[path]},[self.insertion(1,1)]).code,ErrorCode.INVALID_ARGUMENT)
    def test_mixed_revisions_use_original_indices_and_keep_other_paths(self):
        planned=plan_curve_topology(self.before,[self.insertion(1,3),self.insertion(2,1)],[self.deletion(2)])
        self.assertEqual(planned['inserted_count'],2); self.assertEqual(planned['deleted_count'],1)
        self.assertEqual(planned['paths'][0]['segments'][1]['end'],{'x':1.,'y':2.})
        self.assertEqual(planned['paths'][1]['segments'][0]['end'],{'x':2.,'y':3.})
    def test_native_revision_preserves_source_and_copied_basic_appearance(self):
        self.source.curve.paths[1].nodes[0].Type=2
        self.before=self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
        signature=self.bridge._vector_source_signature(self.document,self.source)
        result=self.revise([self.insertion()],result_name='RefinedLogo')
        self.assertEqual(result['created_count'],1); self.assertEqual(result['objects'][0]['object']['object_name'],'RefinedLogo')
        self.assertEqual(result['objects'][0]['curve']['node_count'],7)
        self.assertTrue(result['source_preservation']['verified']); self.assertEqual(result['source_fingerprint'],self.before['fingerprint'])
        self.assertEqual(self.bridge._vector_source_signature(self.document,self.source),signature)
        self.assertTrue(all(code==0 for row in result['objects'][0]['curve']['node_types'] for code in row))
        output=self.app.duplicates[-1]; self.assertIsNot(output.Curve,self.source.Curve)
        self.assertEqual(output.Fill,self.source.Fill); self.assertEqual(output.Outline,self.source.Outline)
        self.assertEqual(self.document.Unit,3); self.assertEqual(self.document.ReferencePoint,9)
    def test_primitive_revision_converts_only_the_independent_copy(self):
        self.source.Type=1
        self.reference=self.bridge.get_object_info(object_name='TopologySource')['object']['object_reference']
        self.before=self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
        result=self.revise([self.insertion(1,1)])
        self.assertEqual(self.source.Type,1); self.assertTrue(result['objects'][0]['editable'])
    def test_stale_geometry_and_invalid_names_fail_before_copying(self):
        self.source.curve.paths[0].nodes[0].PositionX=.1
        self.assertEqual(self.error(self.revise,[self.insertion()]).code,ErrorCode.INVALID_ARGUMENT)
        self.before=self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
        for name in (True,'x'*121,'x\n'):
            self.assertEqual(self.error(self.revise,[self.insertion()],result_name=name).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_missing_native_assignment_is_a_preflight_refusal(self):
        with patch.object(Curve,'CopyAssign',None):
            self.assertEqual(self.error(self.revise,[self.insertion()]).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.app.duplicates,[])
    def test_native_assignment_failures_discard_only_owned_output(self):
        baseline=list(self.layer.Shapes.items)
        for flag in ('copy_assign_failure','ignore_copy_assign','corrupt_copy_assign'):
            setattr(self.app,flag,True)
            failure=self.error(self.revise,[self.insertion()])
            self.assertTrue(failure.details['rollback']['verified'])
            self.assertEqual(self.layer.Shapes.items,baseline)
            self.assertEqual(self.bridge.get_curve_geometry(object_reference=self.reference)['curve'],self.before)
            setattr(self.app,flag,False)
    def test_shared_native_curves_are_refused_before_assignment(self):
        self.app.share_curve=True
        failure=self.error(self.revise,[self.insertion()]); self.assertTrue(failure.details['rollback']['verified'])
        self.assertEqual(self.bridge.get_curve_geometry(object_reference=self.reference)['curve'],self.before)
    def test_source_corruption_requires_worker_recovery(self):
        self.app.mutate_original=True
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.revise_curve_topology(self.reference,self.before['fingerprint'],[self.insertion()])
                self.assertFalse(result['ok']); self.assertFalse(result['error']['details']['rollback']['verified'])
                self.assertEqual(server.rotate_object(20,object_name='TopologySource')['error']['code'],'RECOVERY_REQUIRED')
        finally: dispatcher.close()
    def test_verified_owned_cleanup_allows_subsequent_mutations(self):
        self.app.copy_assign_failure=True
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.revise_curve_topology(self.reference,self.before['fingerprint'],[self.insertion()])
                self.assertFalse(result['ok']); self.app.copy_assign_failure=False
                self.assertTrue(server.revise_curve_topology(self.reference,self.before['fingerprint'],[self.insertion()])['ok'])
        finally: dispatcher.close()
    def test_live_closed_document_reference_is_not_replaced_by_active_document(self):
        self.app.Documents.items=[]
        self.assertEqual(self.error(self.revise,[self.insertion()]).code,ErrorCode.NO_TARGET_DOCUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_registered_schemas_accept_success_and_reject_ambiguous_requests(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool=next(t for t in registry['tools'] if t['name']=='revise_curve_topology')
        schema={'schema_definitions':registry['schema_definitions'],**tool['input_schema']}
        validator=Draft202012Validator(schema)
        request={'object_reference':self.reference,'expected_fingerprint':self.before['fingerprint'],'insertions':[self.insertion()]}
        validator.validate(request)
        for fields in ({'insertions':[]},{'insertions':[self.insertion(t=0)]},{'insertions':[self.insertion(t=True)]},{'insertions':None}):
            with self.assertRaises(ValidationError): validator.validate({**request,**fields})
        result=self.revise([self.insertion()])
        Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tool['output_schema']}).validate(success_result('revise_curve_topology',result,1))


if __name__=='__main__': unittest.main()
