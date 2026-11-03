from __future__ import annotations
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator,ValidationError

from corel_operator import server
from corel_operator.errors import CorelBridgeError,ErrorCode
from corel_operator.results import success_result
from test_layout import Collection
import test_process_colors as process_fakes


class Transparency:
    def __setattr__(self,name,value):
        if name=='AppliedTo' and getattr(self,'ignore_scope',False): return
        if name=='MergeMode' and getattr(self,'ignore_merge',False): return
        super().__setattr__(name,value)
    def __init__(self,shape):
        self.shape=shape; self.Type=0; self.Uniform=0; self.AppliedTo=0; self.MergeMode=0
        self.calls=[]; self.ignore=False; self.fail=False; self.corrupt=False; self.other=False
    def ApplyUniformTransparency(self,value):
        self.calls.append(('uniform',value))
        if self.ignore: return
        self.Type=1; self.Uniform=value
        if self.corrupt: self.shape.curve.paths[0].nodes[0].PositionX+=.1
        if self.other: self.shape.Outline.Width=.1
        if self.fail: raise RuntimeError('Private C:/secret/source.cdr')
    def ApplyNoTransparency(self):
        self.calls.append(('none',))
        if not self.ignore: self.Type=0


class TransparencyTests(unittest.TestCase):
    def setUp(self):
        fixture=process_fakes.ProcessColorTests(); fixture.setUp()
        self.app,self.document,self.source,self.bridge,self.reference=fixture.app,fixture.document,fixture.source,fixture.bridge,fixture.reference
        self.source.Transparency=Transparency(self.source); self.native=self.source.Transparency
    def apply(self,percent=40,**kwargs): return self.bridge.set_uniform_transparency(percent,object_reference=self.reference,**kwargs)
    def inspect(self): return self.bridge.get_transparency(object_reference=self.reference)
    def error(self,call,*args,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught: call(*args,**kwargs)
        return caught.exception
    def test_no_effect_inspection_does_not_read_irrelevant_uniform_properties(self):
        del self.native.Uniform
        value=self.inspect()['transparency']
        self.assertEqual(value['type'],'none'); self.assertIsNone(value['uniform_percent']); self.assertEqual(self.native.calls,[])
    def test_uniform_inspection_reports_percentage_scope_and_merge_mode(self):
        self.native.Type=1; self.native.Uniform=65; self.native.AppliedTo=2; self.native.MergeMode=9
        value=self.inspect()['transparency']
        self.assertEqual(value['uniform_percent'],65); self.assertEqual(value['applied_to'],'both')
        self.assertEqual(value['merge_mode_code'],9); self.assertEqual(value['merge_mode'],'other_or_unavailable')
    def test_missing_and_invalid_native_properties_are_explicit(self):
        del self.source.Transparency
        value=self.inspect()['transparency']; self.assertFalse(value['available']); self.assertEqual(value['type'],'unknown')
        self.source.Transparency=self.native; self.native.Type=1; self.native.Uniform=True
        self.assertIsNone(self.inspect()['transparency']['uniform_percent'])
    def test_nonuniform_inspection_retains_type_without_claiming_uniform_percentage(self):
        self.native.Type=2; self.native.Uniform=50
        value=self.inspect()['transparency']; self.assertEqual(value['type'],'fountain'); self.assertIsNone(value['uniform_percent'])
    def test_uniform_fill_outline_and_both_preserve_complete_vector_geometry(self):
        before=self.bridge.get_curve_geometry(object_reference=self.reference)['curve']
        appearance=(self.bridge._fill_readback(self.source),self.bridge._outline_readback(self.source))
        for scope in ('fill','outline','both'):
            result=self.apply(75,applied_to=scope)
            self.assertEqual(result['transparency']['applied_to'],scope)
            self.assertEqual(result['transparency']['uniform_percent'],75); self.assertEqual(result['transparency']['merge_mode_code'],0)
            self.assertEqual(self.bridge.get_curve_geometry(object_reference=self.reference)['curve'],before)
            self.assertEqual((self.bridge._fill_readback(self.source),self.bridge._outline_readback(self.source)),appearance)
            self.assertEqual(self.document.Unit,3); self.assertEqual(self.document.ReferencePoint,9)
    def test_zero_removes_effect_and_full_transparency_retains_100(self):
        self.assertEqual(self.apply(100)['transparency']['uniform_percent'],100)
        result=self.apply(0); self.assertTrue(result['removed']); self.assertEqual(result['transparency']['type'],'none')
        self.assertEqual(self.native.calls,[('uniform',100),('none',)])
    def test_nonuniform_replacement_and_removal_require_explicit_intent(self):
        self.native.Type=3
        for percent in (0,50): self.assertEqual(self.error(self.apply,percent).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.native.calls,[])
        self.assertEqual(self.apply(50,replace_existing=True)['transparency']['type'],'uniform')
    def test_invalid_percent_scopes_and_intent_are_preflight_refusals(self):
        for percent in (-1,101,True,40.,float('nan')):
            self.assertEqual(self.error(self.apply,percent).code,ErrorCode.INVALID_ARGUMENT)
        for kwargs in ({'applied_to':'all'},{'applied_to':True},{'replace_existing':1}):
            self.assertEqual(self.error(self.apply,**kwargs).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.native.calls,[])
    def test_missing_native_state_and_methods_fail_before_writing(self):
        self.native.Type=99
        self.assertEqual(self.error(self.apply).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.native.Type=0
        with patch.object(Transparency,'ApplyUniformTransparency',None):
            self.assertEqual(self.error(self.apply).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.native.calls,[])
    def test_non_normal_uniform_effect_is_explicitly_reset_to_normal(self):
        self.native.Type=1; self.native.MergeMode=9
        result=self.apply(30); self.assertEqual(result['before_transparency']['merge_mode_code'],9)
        self.assertEqual(result['transparency']['merge_mode'],'normal')
    def test_ignored_native_application_and_removal_fail_readback(self):
        self.native.ignore=True
        self.assertEqual(self.error(self.apply).code,ErrorCode.COREL_COM_ERROR)
        self.native.Type=1
        self.assertEqual(self.error(self.apply,0).code,ErrorCode.COREL_COM_ERROR)
    def test_ignored_scope_and_merge_writes_cannot_pass_percentage_only_checks(self):
        self.native.ignore_scope=True
        self.assertEqual(self.error(self.apply,applied_to='both').code,ErrorCode.COREL_COM_ERROR)
        self.native.ignore_scope=False; self.native.MergeMode=9; self.native.ignore_merge=True
        self.assertEqual(self.error(self.apply).code,ErrorCode.COREL_COM_ERROR)
    def test_unexpected_geometry_or_base_appearance_changes_fail_verification(self):
        for flag in ('corrupt','other'):
            self.setUp(); setattr(self.native,flag,True)
            failure=self.error(self.apply); self.assertFalse(failure.details['rollback']['verified'])
    def test_bitmap_transparency_preserves_measured_bounds(self):
        self.source.Type=5; self.reference=self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']
        before=self.bridge._layout_snapshot(self.document,self.source)
        self.assertTrue(self.apply()['preservation_verified']); self.assertEqual(self.bridge._layout_snapshot(self.document,self.source),before)
    def test_group_transparency_requires_a_separate_workflow(self):
        self.source.Type=7; self.source.Shapes=Collection()
        self.reference=self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']
        self.assertEqual(self.error(self.apply).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.native.calls,[])
    def test_closed_target_never_falls_back_to_an_active_document(self):
        self.app.Documents.items=[]
        self.assertEqual(self.error(self.apply).code,ErrorCode.NO_TARGET_DOCUMENT)
        self.assertEqual(self.native.calls,[])
    def test_uncertain_native_failure_quarantines_writes_but_allows_inspection(self):
        self.native.fail=True
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.set_uniform_transparency(50,object_reference=self.reference)
                self.assertFalse(result['ok']); self.assertNotIn('secret',str(result))
                self.assertEqual(server.rotate_object(20,object_name='ProcessSource')['error']['code'],'RECOVERY_REQUIRED')
                self.assertTrue(server.get_transparency(object_reference=self.reference)['ok'])
        finally: dispatcher.close()
    def test_registered_transparency_schemas_and_results_are_strict(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tools={t['name']:t for t in registry['tools']}
        validator=Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tools['set_uniform_transparency']['input_schema']})
        validator.validate({'percent':50,'object_reference':self.reference})
        for value in (True,101,20.5):
            with self.assertRaises(ValidationError): validator.validate({'percent':value,'object_reference':self.reference})
        for name,result in (('get_transparency',self.inspect()),('set_uniform_transparency',self.apply())):
            validator=Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tools[name]['output_schema']})
            validator.validate(success_result(name,result,1)); invalid=copy.deepcopy(result); invalid['unexpected']=1
            with self.assertRaises(ValidationError): validator.validate(success_result(name,invalid,1))


if __name__=='__main__': unittest.main()
