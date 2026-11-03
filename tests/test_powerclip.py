from __future__ import annotations
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from jsonschema import Draft202012Validator,ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError,ErrorCode
from corel_operator.results import success_result
from test_layout import Collection
from powerclip_fakes import fixture,Shape,Clip,rectangle


class PowerClipTests(unittest.TestCase):
    def setUp(self):
        self.app,self.document,self.layer,self.frame,self.artwork=fixture()
        self.bridge=CorelBridge(); self.bridge.app=self.app; self.bridge._bind_target_document(self.document)
        self.frame_ref=self.ref(self.frame); self.art_ref=self.ref(self.artwork)
    def ref(self,shape): return self.bridge.get_object_info(object_name=shape.Name)['object']['object_reference']
    def create(self,**kwargs): return self.bridge.create_powerclip(self.frame_ref,[self.art_ref],**kwargs)
    def error(self,call,*args,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught: call(*args,**kwargs)
        return caught.exception
    def clip_source(self):
        self.artwork.AddToPowerClip(self.frame,0); self.frame.PowerClip.ContentsLocked=True
        return self.bridge.get_powerclip(object_reference=self.frame_ref)['powerclip']
    def test_inspection_reports_complete_native_clip_tree_without_mutation(self):
        before=self.clip_source(); calls=list(self.app.calls)
        result=self.bridge.get_powerclip(object_reference=self.frame_ref)['powerclip']
        self.assertEqual(result,before); self.assertTrue(result['has_powerclip']); self.assertEqual(result['shape_count'],2)
        self.assertEqual(result['frame']['clip_children'][0]['object_name'],'Artwork'); self.assertEqual(self.app.calls,calls)
    def test_regular_frame_inspection_is_explicitly_unclipped(self):
        result=self.bridge.get_powerclip(object_reference=self.frame_ref)['powerclip']
        self.assertFalse(result['has_powerclip']); self.assertEqual(result['frame']['clip_children'],[])
    def test_creation_preserves_source_frame_and_artwork_native_types_and_geometry(self):
        before=[self.bridge._clip_tree(self.document,s)[0] for s in (self.frame,self.artwork)]
        result=self.create(result_name='EditableClip')
        self.assertEqual(result['created_count'],1); self.assertTrue(result['source_preservation']['verified'])
        tree=result['objects'][0]['powerclip']['frame']; self.assertEqual(tree['shape_type_code'],1)
        self.assertEqual(tree['clip_children'][0]['shape_type_code'],3); self.assertTrue(tree['contents_locked'])
        self.assertEqual([self.bridge._clip_tree(self.document,s)[0] for s in (self.frame,self.artwork)],before)
        self.assertIsNone(self.frame.PowerClip); self.assertIsNone(self.artwork.clip_owner)
        self.assertEqual(self.app.calls[-1][-1],0); self.assertEqual(self.document.Unit,3); self.assertEqual(self.document.ReferencePoint,9)
    def test_contain_and_cover_follow_exact_affine_geometry(self):
        for kind,expected,scale in (('contain',{'x':1.,'y':2.,'width':4.,'height':2.},1.),
                                    ('cover',{'x':-1.,'y':1.,'width':8.,'height':4.},2.)):
            result=self.create(fit_kind=kind)
            payload=result['objects'][0]['powerclip']['frame']['clip_children'][0]
            self.assertEqual(payload['transform']['bounds_inches'],expected); self.assertEqual(result['fit']['scale'],scale)
            self.assertEqual(payload['curve']['paths'][0]['start'],{'x':expected['x'],'y':expected['y']})
    def test_padding_reduces_fitting_area_and_centers_content(self):
        result=self.create(fit_kind='contain',padding_inches=.5)
        self.assertEqual(result['fit']['planned_content_bounds_inches'],{'x':1.5,'y':2.25,'width':3.,'height':1.5})
    def test_multi_object_payload_retains_source_order_and_editable_text_bitmap(self):
        text=Shape(self.layer,[rectangle(0,3,2,1)],'Title',6)
        bitmap=Shape(self.layer,[rectangle(0,4,2,1)],'Photo',5)
        result=self.bridge.create_powerclip(self.frame_ref,[self.ref(bitmap),self.ref(text),self.art_ref],fit_kind='contain')
        payload=result['objects'][0]['powerclip']['frame']['clip_children'][0]
        self.assertEqual(payload['shape_type_code'],7)
        self.assertEqual([n['object_name'] for n in payload['group_children']],['Artwork','Title','Photo'])
        self.assertEqual(payload['group_children'][1]['text']['preview'],'Editable artwork')
        self.assertEqual(payload['group_children'][2]['bitmap']['SizeWidth'],600)
        self.assertEqual(text.Type,6); self.assertEqual(bitmap.Type,5)
    def test_nested_groups_and_unlocked_clips_fit_as_one_complete_assembly(self):
        nested_frame=Shape(self.layer,[rectangle(0,0,2,2)],'NestedFrame',2)
        nested_content=Shape(self.layer,[rectangle(-1,-1,4,4)],'NestedArtwork',3)
        nested_content.AddToPowerClip(nested_frame,0); nested_frame.PowerClip.ContentsLocked=False
        group=Shape(self.layer,name='NestedGroup',code=7); group.attach_group(nested_frame)
        result=self.bridge.create_powerclip(self.frame_ref,[self.ref(group)],fit_kind='contain')
        nested=result['objects'][0]['powerclip']['frame']['clip_children'][0]['group_children'][0]
        self.assertFalse(nested['contents_locked'])
        self.assertEqual(nested['clip_children'][0]['transform']['bounds_inches'],{'x':-1.,'y':-1.,'width':8.,'height':8.})
        self.assertFalse(nested_frame.PowerClip.ContentsLocked)
    def test_extraction_returns_independent_root_references_and_preserves_original_clip(self):
        inspected=self.clip_source(); before=self.bridge._clip_tree(self.document,self.frame)[0]
        result=self.bridge.extract_powerclip_contents(self.frame_ref,inspected['fingerprint'],'Piece')
        self.assertEqual(result['extracted_count'],1)
        output=result['objects'][0]['object']; self.assertEqual(output['object_name'],'Piece_001')
        shape,_=self.bridge._resolve_object_reference(self.document,output['object_reference'],mutation=True)
        self.assertIsNone(shape.clip_owner); self.assertIsNot(shape,self.artwork)
        self.assertEqual(self.bridge._clip_tree(self.document,self.frame)[0],before)
        self.assertTrue(self.frame.PowerClip.ContentsLocked)
    def test_native_reversed_extraction_order_is_reconciled_by_identity(self):
        self.clip_source(); photo=Shape(self.layer,[rectangle(2,2,1,1)],'Second',5); photo.AddToPowerClip(self.frame,0)
        inspected=self.bridge.get_powerclip(object_reference=self.frame_ref)['powerclip']; self.app.reverse_extract=True
        result=self.bridge.extract_powerclip_contents(self.frame_ref,inspected['fingerprint'],'Ordered')
        self.assertEqual([n['object']['object_name'] for n in result['objects']],['Ordered_001','Ordered_002'])
        self.assertEqual([n['powerclip']['frame']['shape_type_code'] for n in result['objects']],[3,5])
    def test_rebuild_cycle_uses_extracted_edits_and_explicit_owned_content_replacement(self):
        inspected=self.clip_source(); extracted=self.bridge.extract_powerclip_contents(self.frame_ref,inspected['fingerprint'])
        content_ref=extracted['objects'][0]['object']['object_reference']
        shape,_=self.bridge._resolve_object_reference(self.document,content_ref,mutation=True); shape.SetPosition(8,8)
        failure=self.error(self.bridge.create_powerclip,self.frame_ref,[content_ref]); self.assertEqual(failure.code,ErrorCode.INVALID_ARGUMENT)
        before=self.bridge._clip_tree(self.document,self.frame)[0]
        result=self.bridge.create_powerclip(self.frame_ref,[content_ref],replace_existing_contents=True,fit_kind='contain')
        self.assertEqual(result['objects'][0]['powerclip']['frame']['clip_children'][0]['transform']['bounds_inches'],{'x':1.,'y':2.,'width':4.,'height':2.})
        self.assertEqual(self.bridge._clip_tree(self.document,self.frame)[0],before)
    def test_stale_clip_fingerprint_and_bad_requests_fail_before_copying(self):
        inspected=self.clip_source(); self.artwork.curve.paths[0].nodes[0].PositionX=.1
        self.assertEqual(self.error(self.bridge.extract_powerclip_contents,self.frame_ref,inspected['fingerprint']).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_invalid_fit_names_and_padding_are_preflight_refusals(self):
        for kwargs in ({'fit_kind':'stretch'},{'contents_locked':1},{'padding_inches':True},{'padding_inches':2},
                       {'fit_kind':'none','padding_inches':.1},{'result_name':'x\n'}):
            self.assertEqual(self.error(self.create,**kwargs).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_open_frames_and_conflicting_input_identity_fail_preflight(self):
        self.frame.Type=3; self.frame.curve.paths[0].closed=False; self.frame.curve.paths[0].segments.pop()
        self.frame_ref=self.ref(self.frame)
        self.assertEqual(self.error(self.create).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.error(self.bridge.create_powerclip,self.frame_ref,[self.frame_ref]).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_wrong_clip_parent_unreadable_state_and_cycles_cannot_be_assumed_absent(self):
        self.frame.PowerClip=Clip(self.artwork)
        self.assertEqual(self.error(self.bridge.get_powerclip,object_reference=self.frame_ref).code,ErrorCode.COREL_COM_ERROR)
        self.frame.PowerClip=None; del self.artwork.PowerClip
        self.assertEqual(self.error(self.create).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
    def test_reused_copy_and_shared_native_curve_data_never_modify_originals(self):
        self.app.reuse_duplicate=True
        failure=self.error(self.create); self.assertFalse(failure.details['rollback']['verified'])
        self.assertEqual(len(self.layer.Shapes.items),2)
        self.app.reuse_duplicate=False; self.app.share_curve=True
        failure=self.error(self.create); self.assertTrue(failure.details['rollback']['verified'])
        self.assertEqual(len(self.layer.Shapes.items),2); self.assertIsNone(self.frame.PowerClip)
    def test_foreign_group_children_prevent_destructive_cleanup(self):
        group=Shape(self.layer,name='SourceGroup',code=7); group.attach_group(self.artwork)
        group_ref=self.ref(group); self.app.share_duplicate_child=True
        failure=self.error(self.bridge.create_powerclip,self.frame_ref,[group_ref])
        self.assertFalse(failure.details['rollback']['verified']); self.assertIn(self.artwork,group.Shapes.items)
        self.assertIs(self.artwork.ParentGroup,group)
    def test_native_clip_failures_and_ignored_centering_are_safely_discarded(self):
        baseline=list(self.layer.Shapes.items)
        for flag in ('clip_failure','ignore_clip','force_center'):
            setattr(self.app,flag,True)
            failure=self.error(self.create); self.assertTrue(failure.details['rollback']['verified'])
            self.assertEqual(self.layer.Shapes.items,baseline); setattr(self.app,flag,False)
    def test_ignored_fitting_and_changed_group_order_fail_complete_geometry_checks(self):
        self.app.ignore_fit=True
        self.assertTrue(self.error(self.create,fit_kind='cover').details['rollback']['verified'])
        self.app.ignore_fit=False; self.app.reverse_group=True
        photo=Shape(self.layer,[rectangle(1,5,1,1)],'Photo',5)
        failure=self.error(self.bridge.create_powerclip,self.frame_ref,[self.art_ref,self.ref(photo)])
        self.assertTrue(failure.details['rollback']['verified'])
    def test_extraction_failures_do_not_claim_corrupted_output_as_success(self):
        inspected=self.clip_source(); before=self.bridge._clip_tree(self.document,self.frame)[0]
        for flag in ('extract_failure','ignore_extract','corrupt_extract','alias_extract'):
            setattr(self.app,flag,True)
            failure=self.error(self.bridge.extract_powerclip_contents,self.frame_ref,inspected['fingerprint'])
            self.assertTrue(failure.details['rollback']['verified'])
            self.assertEqual(self.bridge._clip_tree(self.document,self.frame)[0],before); setattr(self.app,flag,False)
    def test_unknown_outputs_or_source_corruption_require_recovery(self):
        self.app.mutate_original=True
        failure=self.error(self.create); self.assertFalse(failure.details['rollback']['verified'])
        self.setUp(); self.app.extra_output=True
        failure=self.error(self.create); self.assertFalse(failure.details['rollback']['verified'])
        self.assertEqual([s.Name for s in self.layer.Shapes.items],['Frame','Artwork','UnknownExtra'])
    def test_partial_native_failure_quarantines_but_powerclip_inspection_remains_available(self):
        self.app.mutate_original=True
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.create_powerclip(self.frame_ref,[self.art_ref])
                self.assertFalse(result['ok']); self.assertNotIn('secret',str(result))
                self.assertEqual(server.rotate_object(20,object_name='Frame')['error']['code'],'RECOVERY_REQUIRED')
                self.assertTrue(server.get_powerclip(object_reference=self.frame_ref)['ok'])
        finally: dispatcher.close()
    def test_closed_targets_and_different_layers_fail_before_copying(self):
        self.app.Documents.items=[]
        self.assertEqual(self.error(self.create).code,ErrorCode.NO_TARGET_DOCUMENT)
        self.assertEqual(self.app.duplicates,[])
        self.setUp()
        from test_template_jobs import Layer
        other=Layer(self.document.ActivePage,'Other'); self.document.ActivePage.AllLayers.items.append(other)
        artwork=Shape(other,[rectangle()],'OtherArtwork')
        self.assertEqual(self.error(self.bridge.create_powerclip,self.frame_ref,[self.ref(artwork)]).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_shared_other_source_geometry_and_shared_stories_are_refused_before_fit(self):
        self.app.other=Shape(self.layer,[rectangle(0,0,4,2)],'OtherCurve')
        self.app.share_other_curve=True
        failure=self.error(self.create,fit_kind='cover'); self.assertTrue(failure.details['rollback']['verified'])
        self.app.share_other_curve=False
        title=Shape(self.layer,[rectangle(0,0,4,2)],'SharedTitle',6); self.app.share_story=True
        failure=self.error(self.bridge.create_powerclip,self.frame_ref,[self.ref(title)],fit_kind='cover')
        self.assertTrue(failure.details['rollback']['verified']); self.assertEqual(title.Text.Story.Size,18.)
    def test_copy_peak_budget_is_checked_before_native_duplication(self):
        group=Shape(self.layer,name='BudgetGroup',code=7); group.attach_group(self.artwork)
        extra=Shape(self.layer,[rectangle(3,3)],'GroupChild'); group.attach_group(extra)
        reference=self.ref(group)
        with patch('corel_operator.powerclip_bridge.MAX_CLIP_SHAPES',8):
            failure=self.error(self.bridge.create_powerclip,self.frame_ref,[reference])
        self.assertEqual(failure.code,ErrorCode.UNSUPPORTED_IN_PROFILE); self.assertEqual(self.app.duplicates,[])
    def test_unreadable_methods_and_linked_paragraphs_are_preflight_refusals(self):
        with patch.object(Shape,'AddToPowerClip',None):
            self.assertEqual(self.error(self.create).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        title=Shape(self.layer,[rectangle()],'LinkedTitle',6)
        title.Text.Type=1; title.Text.Frames=Collection(object(),object())
        self.assertEqual(self.error(self.bridge.create_powerclip,self.frame_ref,[self.ref(title)]).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.app.duplicates,[])
    def test_group_cycles_and_excessive_depth_fail_bounded_tree_inspection(self):
        group=Shape(self.layer,name='Cycle',code=7); group.Shapes.items.append(group)
        self.assertEqual(self.error(self.bridge._clip_tree,self.document,group).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        group.Shapes.items=[]
        child=Shape(self.layer,name='Deep',code=7); group.attach_group(child)
        with patch('corel_operator.powerclip_bridge.MAX_CLIP_DEPTH',0):
            self.assertEqual(self.error(self.bridge._clip_tree,self.document,group).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
    def test_long_text_tail_changes_are_bound_to_the_whole_story_fingerprint(self):
        title=Shape(self.layer,[rectangle()],'LongText',6); title.Text.Story.Text='x'*4000+'A'
        title.AddToPowerClip(self.frame,0)
        inspected=self.bridge.get_powerclip(object_reference=self.frame_ref)['powerclip']
        self.assertEqual(len(inspected['frame']['clip_children'][0]['text']['preview']),4000)
        title.Text.Story.Text='x'*4000+'B'
        self.assertEqual(self.error(self.bridge.extract_powerclip_contents,self.frame_ref,inspected['fingerprint']).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.app.duplicates,[])
    def test_failed_cleanup_is_explicit_and_does_not_report_source_rollback(self):
        self.app.clip_failure=True; self.app.fail_delete=True
        failure=self.error(self.create); self.assertFalse(failure.details['rollback']['verified'])
        self.assertEqual(failure.details['rollback']['error_type'],'RuntimeError')
        self.assertIsNone(self.frame.PowerClip)
    def test_explicit_unlocked_outputs_retain_requested_lock_state(self):
        result=self.create(contents_locked=False)
        self.assertFalse(result['objects'][0]['powerclip']['frame']['contents_locked'])
    def test_native_copy_name_changes_are_normalized_only_on_owned_descendants(self):
        group=Shape(self.layer,name='NamedGroup',code=7); group.attach_group(self.artwork)
        self.app.rename_copies=True
        result=self.bridge.create_powerclip(self.frame_ref,[self.ref(group)])
        payload=result['objects'][0]['powerclip']['frame']['clip_children'][0]
        self.assertEqual(payload['object_name'],'NamedGroup'); self.assertEqual(payload['group_children'][0]['object_name'],'Artwork')
        self.assertEqual(self.artwork.Name,'Artwork'); self.assertEqual(group.Name,'NamedGroup')
    def test_non_root_copy_returns_are_not_claimed_as_owned_scene_objects(self):
        self.app.detach_duplicate=True
        failure=self.error(self.create)
        self.assertTrue(failure.details['ownership_uncertain']); self.assertFalse(failure.details['rollback']['verified'])
        self.assertEqual([shape.Name for shape in self.layer.Shapes.items],['Frame','Artwork'])
    def test_unrelated_outline_weight_changes_cannot_pass_fitting_checks(self):
        self.artwork.Outline=SimpleNamespace(Type=1,Width=.02,Color=SimpleNamespace(Type=5,RGBRed=10,RGBGreen=20,RGBBlue=30))
        self.app.corrupt_fit_outline=True
        failure=self.error(self.create,fit_kind='cover')
        self.assertTrue(failure.details['rollback']['verified']); self.assertEqual(self.artwork.Outline.Width,.02)
    def test_unrelated_text_size_changes_cannot_pass_fitting_checks(self):
        title=Shape(self.layer,[rectangle(0,0,4,2)],'FitTitle',6); self.app.corrupt_fit_text=True
        failure=self.error(self.bridge.create_powerclip,self.frame_ref,[self.ref(title)],fit_kind='cover')
        self.assertTrue(failure.details['rollback']['verified']); self.assertEqual(title.Text.Story.Size,18.)
    def test_registered_recursive_tree_schemas_and_requests_are_strict(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tools={tool['name']:tool for tool in registry['tools']}
        values={'get_powerclip':self.bridge.get_powerclip(object_reference=self.frame_ref),'create_powerclip':self.create()}
        clipped=values['create_powerclip']['objects'][0]
        values['extract_powerclip_contents']=self.bridge.extract_powerclip_contents(clipped['object']['object_reference'],clipped['powerclip']['fingerprint'])
        for name,value in values.items():
            validator=Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tools[name]['output_schema']})
            validator.validate(success_result(name,value,1)); bad=copy.deepcopy(value); bad['unexpected']=1
            with self.assertRaises(ValidationError): validator.validate(success_result(name,bad,1))
        schema={'schema_definitions':registry['schema_definitions'],**tools['create_powerclip']['input_schema']}
        validator=Draft202012Validator(schema)
        request={'frame_reference':self.frame_ref,'content_references':[self.art_ref]}; validator.validate(request)
        for fields in ({'content_references':[]},{'fit_kind':'stretch'},{'padding_inches':True},{'contents_locked':1}):
            with self.assertRaises(ValidationError): validator.validate({**request,**fields})


if __name__=='__main__': unittest.main()
