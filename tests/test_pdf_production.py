from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,NumberObject,ArrayObject,DecodedStreamObject
from jsonschema import Draft202012Validator,ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError,ErrorCode
from corel_operator.pdf_inspection import inspect_pdf
from corel_operator.results import success_result
from test_template_jobs import App,Document


def write_pdf(path,sizes=((8.5,11),),font=None,form=False,rotation=0,encrypt=False):
    writer=PdfWriter()
    for width,height in sizes:
        page=writer.add_blank_page(width*72,height*72)
        if rotation: page.rotate(rotation)
        if font:
            native=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            if font=='embedded':
                stream=DecodedStreamObject(); stream.set_data(b'SYNTHETIC FONT PROGRAM')
                descriptor=DictionaryObject({NameObject('/FontFile'):writer._add_object(stream)})
                native[NameObject('/FontDescriptor')]=writer._add_object(descriptor)
            resources=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(native)})})
            if form:
                xobject=DecodedStreamObject(); xobject.set_data(b'')
                xobject.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),NameObject('/Resources'):resources})
                resources=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Fm'):writer._add_object(xobject)})})
            page[NameObject('/Resources')]=resources
    if encrypt: writer.encrypt('synthetic')
    with open(path,'wb') as stream: writer.write(stream)


class Settings:
    names=('PublishRange ColorMode pdfVersion TextAsCurves EmbedFonts EmbedBaseFonts SubsetFonts IncludeBleed Bleed '
           'CropMarks RegistrationMarks Overprints DensitometerScales FileInformation EncryptType BitmapCompression DownsampleColor '
           'DownsampleGray DownsampleMono UseColorProfile ConvertSpotColors MaintainOPILinks EmbedFile ComplexFillsAsBitmaps '
           'TextExportMode TrueTypeToType1').split()
    def __init__(self):
        self.values={name:True for name in self.names}
        self.values.update(PublishRange=2,ColorMode=1,pdfVersion=8,Bleed=123,EncryptType=1,BitmapCompression=2,TextExportMode=1)
        self.original=dict(self.values); self.ignore=None; self.fail_restore=None; self.writes=[]
    def __getattr__(self,name):
        if name in self.values: return self.values[name]
        raise AttributeError(name)
    def __setattr__(self,name,value):
        if name not in self.names: object.__setattr__(self,name,value); return
        self.writes.append((name,value))
        if name==self.fail_restore and value==self.original[name]: raise RuntimeError('Private C:/secret/client.cdr')
        if name!=self.ignore: self.values[name]=value


class PdfProductionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'job.pdf'
        self.app=App(); self.document=Document(self.app,'Source.cdr')
        self.app.Documents.items=[self.document]; self.app.ActiveDocument=self.document
        self.settings=Settings(); self.document.PDFSettings=self.settings
        self.bridge=CorelBridge(); self.bridge.app=self.app; self.bridge._bind_target_document(self.document)
        self.published=[]
        def publish(path):
            self.published.append((path,dict(self.settings.values)))
            write_pdf(path,sizes=[(page.SizeWidth,page.SizeHeight) for page in self.document.Pages.items],font='embedded')
        self.document.PublishToPDF=publish
    def error(self,code,call,*args,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught: call(*args,**kwargs)
        self.assertEqual(caught.exception.code,code); self.assertNotIn('secret',str(caught.exception))
        return caught.exception
    def test_blank_pdf_and_expected_sizes(self):
        write_pdf(self.path)
        result=inspect_pdf(str(self.path),1,[{'width':8.5,'height':11}],True)
        self.assertTrue(result['checks_passed']); self.assertEqual(result['font_resource_count'],0)
        self.assertFalse(result['production_ready']); self.assertEqual(result['pages'][0]['trim_box_inches'],None)
    def test_every_page_is_checked_despite_summary_truncation(self):
        sizes=[(8.5,11)]*100+[(3,4)]; write_pdf(self.path,sizes=sizes)
        result=inspect_pdf(str(self.path),101,[{'width':8.5,'height':11}]*101)
        self.assertTrue(result['pages_truncated']); self.assertEqual(len(result['pages']),100)
        self.assertFalse(result['checks']['page_sizes_match'])
    def test_font_program_presence_and_nested_form_fonts(self):
        for form in (False,True):
            write_pdf(self.path,font='embedded',form=form)
            result=inspect_pdf(str(self.path),require_embedded_fonts=True)
            self.assertTrue(result['checks_passed']); self.assertEqual(result['font_resource_count'],1)
            write_pdf(self.path,font='unembedded',form=form)
            result=inspect_pdf(str(self.path),require_embedded_fonts=True)
            self.assertFalse(result['checks_passed']); self.assertEqual(result['unembedded_font_count'],1)
    def test_rotation_is_applied_to_effective_dimensions(self):
        write_pdf(self.path,rotation=90)
        result=inspect_pdf(str(self.path),expected_page_sizes=[{'width':11,'height':8.5}])
        self.assertTrue(result['checks_passed'])
    def test_composite_font_descendant_program_is_inspected(self):
        writer=PdfWriter(); page=writer.add_blank_page(72,72)
        program=DecodedStreamObject(); program.set_data(b'SYNTHETIC CID FONT')
        descriptor=DictionaryObject({NameObject('/FontFile2'):writer._add_object(program)})
        descendant=DictionaryObject({NameObject('/FontDescriptor'):writer._add_object(descriptor)})
        font=DictionaryObject({NameObject('/Subtype'):NameObject('/Type0'),NameObject('/BaseFont'):NameObject('/Example'),
            NameObject('/DescendantFonts'):ArrayObject([writer._add_object(descendant)])})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        writer.write(self.path)
        self.assertTrue(inspect_pdf(str(self.path),require_embedded_fonts=True)['checks_passed'])
        del descriptor['/FontFile2']; writer.write(self.path)
        self.assertFalse(inspect_pdf(str(self.path),require_embedded_fonts=True)['checks_passed'])
    def test_optional_boxes_beyond_returned_page_limit_are_validated(self):
        writer=PdfWriter()
        for _ in range(101): page=writer.add_blank_page(72,72)
        page[NameObject('/BleedBox')]=ArrayObject([NumberObject(0)]*4)
        writer.write(self.path)
        self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path))
    def test_malformed_encrypted_and_empty_inputs_are_refused(self):
        for content in (b'',b'%PDF-1.4\ntruncated',b'plain text'):
            self.path.write_bytes(content)
            self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path))
        write_pdf(self.path,encrypt=True)
        self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path))
    def test_page_tree_count_mismatch_and_invalid_boxes_are_refused(self):
        writer=PdfWriter(); page=writer.add_blank_page(72,72)
        page[NameObject('/MediaBox')]=ArrayObject([NumberObject(5),NumberObject(0),NumberObject(1),NumberObject(1)])
        writer.write(self.path)
        self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path))
        writer=PdfWriter(); writer.add_blank_page(72,72)
        writer._pages.get_object()[NameObject('/Count')]=NumberObject(2); writer.write(self.path)
        self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path))
    def test_expectation_validation_precedes_file_access(self):
        for options in ({'expected_page_count':True},{'expected_page_count':501},{'tolerance_inches':float('nan')},
                        {'require_embedded_fonts':1},{'expected_page_count':2,'expected_page_sizes':[{'width':1,'height':1}]}):
            self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path),**options)
        self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,'relative.pdf')
    def test_declared_input_and_resource_bounds(self):
        write_pdf(self.path)
        with patch('corel_operator.pdf_inspection.MAX_PDF_BYTES',8):
            self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path))
        write_pdf(self.path,font='embedded')
        with patch('corel_operator.pdf_inspection.MAX_RESOURCES',2):
            self.error(ErrorCode.INVALID_ARGUMENT,inspect_pdf,str(self.path))
    def test_controlled_export_preserves_source_settings_and_checks_all_pages(self):
        self.document.AddPagesEx(1,6.5,2.5)
        before=dict(self.settings.values); result=self.bridge.export_pdf_controlled(str(self.path))
        self.assertTrue(self.path.exists()); self.assertTrue(result['settings_restored'])
        self.assertEqual(self.settings.values,before); self.assertEqual(result['inspection']['page_count'],2)
        self.assertEqual(self.published[0][1]['PublishRange'],0); self.assertFalse(self.published[0][1]['IncludeBleed'])
        self.assertFalse(result['production_ready']); self.assertTrue(result['inspection']['checks_passed'])
        self.assertEqual(list(Path(self.directory.name).iterdir()),[self.path])
    def test_existing_output_is_preserved_before_setting_writes(self):
        self.path.write_bytes(b'PRESERVE')
        self.error(ErrorCode.OUTPUT_EXISTS,self.bridge.export_pdf_controlled,str(self.path))
        self.assertEqual(self.path.read_bytes(),b'PRESERVE'); self.assertEqual(self.settings.writes,[])
    def test_output_race_is_preserved_and_native_settings_are_restored(self):
        publish=self.document.PublishToPDF
        def racing(path): publish(path); self.path.write_bytes(b'RACE')
        self.document.PublishToPDF=racing
        error=self.error(ErrorCode.OUTPUT_EXISTS,self.bridge.export_pdf_controlled,str(self.path))
        self.assertEqual(self.path.read_bytes(),b'RACE'); self.assertTrue(error.details['rollback']['verified'])
    def test_invalid_native_output_is_discarded_after_restoration(self):
        self.document.PublishToPDF=lambda path:Path(path).write_bytes(b'NOT PDF')
        error=self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.export_pdf_controlled,str(self.path))
        self.assertTrue(error.details['rollback']['verified']); self.assertFalse(self.path.exists())
        self.assertEqual(self.settings.values,self.settings.original)
    def test_native_page_mismatch_and_missing_fonts_block_publication(self):
        for sizes,font in ((((1,1),),'embedded'),(((8.5,11),),'unembedded')):
            self.document.PublishToPDF=lambda path:write_pdf(path,sizes=sizes,font=font)
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.export_pdf_controlled,str(self.path))
            self.assertTrue(error.details['rollback']['verified']); self.assertFalse(self.path.exists())
    def test_ignored_native_controls_block_export(self):
        self.settings.ignore='ColorMode'
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.export_pdf_controlled,str(self.path))
        self.assertTrue(error.details['rollback']['verified']); self.assertFalse(self.published)
    def test_restore_failure_quarantines_the_worker(self):
        self.settings.fail_restore='ColorMode'
        with patch.object(server,'CorelBridge',return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,'dispatcher',dispatcher):
                result=server.export_pdf_controlled(str(self.path))
                self.assertFalse(result['error']['details']['rollback']['verified'])
                self.assertEqual(server.rotate_object(20,object_name='Source')['error']['code'],'RECOVERY_REQUIRED')
        finally: dispatcher.close()
        self.assertFalse(self.path.exists())
    def test_native_failure_is_sanitized_and_settings_restore(self):
        def fail(path): raise RuntimeError('Private C:/secret/client.cdr')
        self.document.PublishToPDF=fail
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.export_pdf_controlled,str(self.path))
        self.assertTrue(error.details['rollback']['verified'])
    def test_export_options_fail_before_native_mutation(self):
        for options in ({'color_mode':[]},{'pdf_version':'X-4'},{'text_as_curves':1},{'require_embedded_fonts':None}):
            self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.export_pdf_controlled,str(self.path),**options)
        self.assertFalse(self.settings.writes)
    def test_unreadable_snapshot_is_refused_before_native_changes(self):
        del self.settings.values['EmbedFonts']
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE,self.bridge.export_pdf_controlled,str(self.path))
        self.assertFalse(self.settings.writes)
    def test_staging_change_is_refused_before_publication(self):
        from corel_operator.pdf_bridge import inspect_pdf as inspect_staged
        def changed(path,*args):
            result=inspect_staged(path,*args); Path(path).write_bytes(b'changed'); return result
        with patch('corel_operator.pdf_bridge.inspect_pdf',changed):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.export_pdf_controlled,str(self.path))
        self.assertTrue(error.details['rollback']['verified']); self.assertFalse(self.path.exists())
    def test_result_schemas_reject_unknown_fields(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/'catalog/mcp_tool_registry.json').read_text(encoding='utf-8'))
        tools={t['name']:t for t in registry['tools']}; result=self.bridge.export_pdf_controlled(str(self.path))
        for name,value in (('export_pdf_controlled',result),('inspect_pdf',result['inspection'])):
            validator=Draft202012Validator({'schema_definitions':registry['schema_definitions'],**tools[name]['output_schema']})
            validator.validate(success_result(name,value,1)); bad=copy.deepcopy(value); bad['unknown']=True
            with self.assertRaises(ValidationError): validator.validate(success_result(name,bad,1))


if __name__=='__main__': unittest.main()
