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
from vector_fakes import fixture,Curve,Shape,rectangle
from test_layout import Collection


def cmyk(c=20,m=40,y=60,k=80): return {'model':'cmyk','cyan':c,'magenta':m,'yellow':y,'black':k}
def rgb(): return {'model':'rgb','red':10,'green':50,'blue':90}
def native_color(value):
    if value['model']=='cmyk': return SimpleNamespace(Type=2,CMYKCyan=value['cyan'],CMYKMagenta=value['magenta'],CMYKYellow=value['yellow'],CMYKBlack=value['black'])
    return SimpleNamespace(Type=5,RGBRed=value['red'],RGBGreen=value['green'],RGBBlue=value['blue'])


class Fill:
    def __init__(self,shape): self.Type=0; self.shape=shape; self.UniformColor=None; self.ignore=False; self.fail=False; self.convert=False; self.mutate=False; self.other=False
    def ApplyUniformFill(self,color):
        if self.ignore: return
        self.Type=1; self.UniformColor=native_color(rgb()) if self.convert else color
        if self.mutate: self.shape.curve.paths[0].nodes[0].PositionX+=.1
        if self.other: self.shape.Outline.Width=.1
        if self.fail: raise RuntimeError('Private C:/secret/source.cdr')


class ProcessColorTests(unittest.TestCase):
    def setUp(self):
        self.app,self.document,self.layer=fixture()
        self.source=Shape(self.layer,Curve.from_paths(self.app,[rectangle()]),'ProcessSource')
        self.source.Fill=Fill(self.source)
        self.source.Outline=SimpleNamespace(Type=1,Width=.01,Color=native_color(rgb()))
        self.app.CreateRGBColor=lambda r,g,b:native_color({'model':'rgb','red':r,'green':g,'blue':b})
        self.app.CreateCMYKColor=lambda c,m,y,k:native_color(cmyk(c,m,y,k))
        self.bridge=CorelBridge(); self.bridge.app=self.app; self.bridge._bind_target_document(self.document)
        self.reference=self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']
    def apply(self,color=None,**kwargs): return self.bridge.set_process_color(color or cmyk(),object_reference=self.reference,**kwargs)
    def error(self,call,*args,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught: call(*args,**kwargs)
        return caught.exception
    def test_cmyk_fill_preserves_native_process_components_and_geometry(self):
        before=self.bridge.get_curve_geometry(object_reference=self.reference)['curve']; outline=self.bridge._outline_readback(self.source)
        result=self.apply(); self.assertEqual(result['actual_color']['model'],'cmyk')
        self.assertEqual(result['actual_color']['value'],{k:v for k,v in cmyk().items() if k!='model'})
        self.assertEqual(self.bridge.get_curve_geometry(object_reference=self.reference)['curve'],before)
        self.assertEqual(result['actual_outline'],outline); self.assertTrue(result['preservation_verified'])
        self.assertEqual(self.document.Unit,3); self.assertEqual(self.document.ReferencePoint,9)
    def test_rgb_fill_uses_the_same_exact_readback_contract(self):
        result=self.apply(rgb()); self.assertEqual(result['actual_color']['value'],{'red':10,'green':50,'blue':90})
    def test_outline_recoloring_preserves_existing_width_and_fill(self):
        self.apply(rgb()); fill=self.bridge._fill_readback(self.source)
        result=self.apply(channel='outline')
        self.assertEqual(result['actual_outline']['width_raw'],.01); self.assertEqual(result['actual_fill'],fill)
        self.assertEqual(result['actual_outline']['color']['model'],'cmyk')
        self.assertEqual(result['actual_outline']['width_units'],'coreldraw_outline_width_unverified')
    def test_non_uniform_fill_replacement_requires_explicit_intent(self):
        self.source.Fill.Type=2
        self.assertEqual(self.error(self.apply).code,ErrorCode.INVALID_ARGUMENT)
        result=self.apply(replace_non_uniform=True); self.assertEqual(result['actual_fill']['type'],'uniform')
    def test_invalid_component_models_types_and_ranges_fail_before_writing(self):
        bad=[cmyk(c=True),cmyk(k=101),cmyk(m=-1),cmyk(y=2.5),{'model':'spot','name':'Pantone'},
             {**rgb(),'blue':256},{**rgb(),'green':float('nan')},{**cmyk(),'red':0},{'model':'cmyk','cyan':0}]
        for value in bad:
            self.assertEqual(self.error(self.bridge.set_process_color,value,object_reference=self.reference).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.source.Fill.Type,0)
    def test_invalid_channels_and_intent_flags_fail_before_assignment(self):
        for kwargs in ({'channel':True},{'channel':'both'},{'replace_non_uniform':1}):
            self.assertEqual(self.error(self.apply,**kwargs).code,ErrorCode.INVALID_ARGUMENT)
        self.assertEqual(self.source.Fill.Type,0)
    def test_absent_enhanced_or_unreadable_outline_is_refused(self):
        for code,width in ((0,.01),(2,.01),(1,0),(1,float('nan'))):
            self.source.Outline.Type=code; self.source.Outline.Width=width
            self.assertEqual(self.error(self.apply,channel='outline').code,ErrorCode.UNSUPPORTED_IN_PROFILE)
    def test_missing_fill_and_factory_methods_are_preflight_refusals(self):
        with patch.object(Fill,'ApplyUniformFill',None):
            self.assertEqual(self.error(self.apply).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.app.CreateCMYKColor=None
        self.assertEqual(self.error(self.apply).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.source.Fill.Type,0)
    def test_factory_model_conversion_is_refused_before_native_shape_assignment(self):
        self.app.CreateCMYKColor=lambda *args:native_color(rgb())
        self.assertEqual(self.error(self.apply).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.source.Fill.Type,0)
    def test_native_ignored_or_converted_colors_fail_complete_readback(self):
        for flag in ('ignore','convert'):
            setattr(self.source.Fill,flag,True)
            result=self.error(self.apply); self.assertEqual(result.code,ErrorCode.COREL_COM_ERROR)
            self.assertFalse(result.details['rollback']['verified']); setattr(self.source.Fill,flag,False)
    def test_unexpected_geometry_or_other_channel_changes_fail_readback(self):
        for flag in ('mutate','other'):
            with self.subTest(flag=flag):
                self.setUp(); setattr(self.source.Fill,flag,True)
                self.assertEqual(self.error(self.apply).code,ErrorCode.COREL_COM_ERROR)
    def test_closed_or_changed_native_targets_do_not_fall_back(self):
        self.app.Documents.items=[]
        self.assertEqual(self.error(self.apply).code,ErrorCode.NO_TARGET_DOCUMENT)
        self.assertEqual(self.source.Fill.Type,0)
    def test_group_and_bitmap_color_assignment_is_explicitly_unsupported(self):
        self.source.Shapes=Collection()
        for code in (7,5):
            self.source.Type=code
            reference=self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']
            self.assertEqual(self.error(self.bridge.set_process_color,cmyk(),object_reference=reference).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
    def test_text_process_fill_preserves_readable_story_properties(self):
        self.source.Type=6
        self.source.Text=SimpleNamespace(Story=SimpleNamespace(Text='Editable title',Font='Arial',Size=18.,Bold=-1))
        self.reference=self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']
        before=self.bridge._text_readback(self.source)
        result=self.apply(); self.assertEqual(result['actual_color']['model'],'cmyk')
        self.assertEqual(self.bridge._text_readback(self.source),before)
    def test_unreadable_text_formatting_fails_before_assignment(self):
        self.source.Type=6; self.source.Text=SimpleNamespace(Story=SimpleNamespace(Text='Editable title'))
        self.reference=self.bridge.get_object_info(object_name='ProcessSource')['object']['object_reference']
        self.assertEqual(self.error(self.apply).code,ErrorCode.UNSUPPORTED_IN_PROFILE)
        self.assertEqual(self.source.Fill.Type,0)
    def test_native_partial_failure_quarantines_subsequent_mutations(self):
        self.source.Fill.fail=True
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.set_process_color(cmyk(),object_reference=self.reference)
                self.assertFalse(result['ok']); self.assertNotIn('secret',str(result))
                self.assertEqual(server.rotate_object(20,object_name='ProcessSource')['error']['code'],'RECOVERY_REQUIRED')
        finally: dispatcher.close()
    def test_unverified_color_readback_also_requires_recovery(self):
        self.source.Fill.ignore=True
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.set_process_color(cmyk(),object_reference=self.reference)
                self.assertFalse(result['ok'])
                self.assertEqual(server.rotate_object(20,object_name='ProcessSource')['error']['code'],'RECOVERY_REQUIRED')
        finally: dispatcher.close()
    def test_registered_color_schema_and_result_are_strict(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tool=next(t for t in registry['tools'] if t['name']=='set_process_color')
        validator=Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tool['input_schema']})
        validator.validate({'color':cmyk(),'object_reference':self.reference})
        for value in (cmyk(c=True),cmyk(k=101),{**cmyk(),'red':2}):
            with self.assertRaises(ValidationError): validator.validate({'color':value,'object_reference':self.reference})
        validator=Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tool['output_schema']})
        result=self.apply(); validator.validate(success_result('set_process_color',result,1))
        invalid=copy.deepcopy(result); invalid['unknown']=True
        with self.assertRaises(ValidationError): validator.validate(success_result('set_process_color',invalid,1))


if __name__=='__main__': unittest.main()
