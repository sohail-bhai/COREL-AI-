from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from jsonschema import Draft202012Validator,ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError,ErrorCode
from corel_operator.template_jobs import read_template_csv,plan_template_batch,seal
from corel_operator.results import success_result
from test_layout import Collection,Shape
from test_typography import Story


class TextStory(Story):
    def __init__(self,app,text):
        super().__init__(text); self.app=app
    def __setattr__(self,name,value):
        super().__setattr__(name,value)
        if name=="Text" and value==self.app.fail_text:
            raise RuntimeError("Private record C:/secret/client.csv")


class TemplateShape(Shape):
    def __init__(self,app,name,code,x,y,w,h,text=""):
        super().__init__(name,app.next_id,x,y,w,h); app.next_id+=1
        self.app=app; self.Type=code; self.Shapes=Collection()
        if code==6: self.Text=SimpleNamespace(Story=TextStory(app,text),Type=0,Overflow=False,Frames=Collection(object()))
        self.Fill=SimpleNamespace(Type=0)
        self.Outline=SimpleNamespace(Type=0,Width=0.)
    def bounds(self):
        if self.Type==7 and self.Shapes.Count:
            bounds=[s.bounds() for s in self.Shapes.items]
            x=min(b[0] for b in bounds); y=min(b[1] for b in bounds)
            return x,y,max(b[0]+b[2] for b in bounds)-x,max(b[1]+b[3] for b in bounds)-y
        if self.Type==6:
            return self.matrix[4],self.matrix[5],len(self.Text.Story.Text)*.05,.2
        return super().bounds()
    def SetPosition(self,x,y):
        if self.Type==7:
            dx=x-self.PositionX; dy=y-self.PositionY
            for child in self.Shapes.items: child.SetPosition(child.PositionX+dx,child.PositionY+dy)
        else: super().SetPosition(x,y)
    def clone(self,layer,parent=None):
        result=TemplateShape(self.app,self.Name,self.Type,self.PositionX,self.PositionY,self.width,self.height,
                             self.Text.Story.Text if self.Type==6 else "")
        result.Layer,result.Page,result.ParentGroup=layer,layer.Page,parent
        if self.Type==6:
            result.Text.Story.__dict__.update({k:v for k,v in self.Text.Story.__dict__.items() if k not in ("app","writes")})
            result.Text.Type=self.Text.Type; result.Text.Overflow=self.Text.Overflow
        result.Shapes=Collection(*[child.clone(layer,result) for child in self.Shapes.items])
        return result
    def Copy(self): self.app.clipboard=self
    def Duplicate(self,x,y):
        result=self.clone(self.Layer)
        self.Layer.Shapes.items.append(result); self.Page.Shapes.items.append(result)
        return result


class Layer:
    def __init__(self,page,name): self.Page=page; self.Name=name; self.Shapes=Collection()
    def Activate(self): self.Page.ActiveLayer=self
    def Paste(self):
        root=self.Page.document.app.clipboard.clone(self)
        self.Shapes.items.append(root); self.Page.Shapes.items.append(root)
        return root


class Page:
    def __init__(self,document,index):
        self.document=document; self.Index=index; self.Shapes=Collection(); self.AllLayers=Collection()
        self.SizeWidth=8.5; self.SizeHeight=11
        self.ActiveLayer=self.CreateLayer("Artwork")
    def Activate(self): self.document.ActivePage=self; self.document.Activate()
    def CreateLayer(self,name):
        layer=Layer(self,name); self.AllLayers.items.append(layer); return layer
    def SetSize(self,w,h): self.SizeWidth=w; self.SizeHeight=h


class Document:
    def __init__(self,app,name,owned=False):
        self.app=app; self.Name=name; self.owned=owned; self.Unit=3; self.ReferencePoint=9; self.Dirty=False
        self.Pages=Collection(); self.ActivePage=Page(self,1); self.Pages.items.append(self.ActivePage)
        self.closed=False; self.commands=[]
    def Activate(self): self.app.ActiveDocument=self
    def BeginCommandGroup(self,name): self.commands.append(name)
    def EndCommandGroup(self): self.commands.append("end")
    def AddPagesEx(self,count,w,h):
        for _ in range(count):
            page=Page(self,self.Pages.Count+1); page.SetSize(w,h); self.Pages.items.append(page)
    def Close(self):
        if not self.owned: raise AssertionError("A pre-existing source document must never be closed")
        if self.app.fail_close: raise RuntimeError("Synthetic close failure")
        self.closed=True; self.app.Documents.items.remove(self)


class App:
    def __init__(self):
        self.next_id=100; self.fail_text=None; self.fail_close=False; self.clipboard=None
        self.FontList=Collection("Arial"); self.Documents=Collection(); self.outputs=[]; self.return_existing=False
    def CreateDocument(self):
        if self.return_existing: return self.Documents.items[0]
        doc=Document(self,f"Output{len(self.outputs)+1}",owned=True)
        self.Documents.items.append(doc); self.outputs.append(doc); self.ActiveDocument=doc
        return doc


class TemplateJobsTests(unittest.TestCase):
    def setUp(self):
        self.app=App(); self.source=Document(self.app,"Source.cdr"); self.other=Document(self.app,"Private.cdr")
        self.app.Documents.items=[self.source,self.other]; self.app.ActiveDocument=self.other
        layer=self.source.ActivePage.ActiveLayer
        self.root=TemplateShape(self.app,"Template",7,1,1,3,2)
        self.root.Page,self.root.Layer=self.source.ActivePage,layer
        children=[TemplateShape(self.app,"Background",1,1,1,3,2),TemplateShape(self.app,"Name",6,1.2,2,1,.2,"NAME"),TemplateShape(self.app,"ID",6,1.2,1.5,1,.2,"ID")]
        for child in children: child.Page,child.Layer,child.ParentGroup=self.root.Page,layer,self.root
        self.root.Shapes=Collection(*children); layer.Shapes.items=[self.root]; self.root.Page.Shapes.items=[self.root]
        self.bridge=CorelBridge(); self.bridge.app=self.app; self.bridge._bind_target_document(self.source)
        self.template=self.bridge.inspect_text_template(object_name="Template")["template"]
        self.records=[{"member":"Alia","number":"001"},{"member":"Bilal","number":"002"},{"member":"Cora","number":"003"}]
    def plan(self,**options):
        defaults=dict(sheet_width_inches=6.5,sheet_height_inches=2.5,gutter_inches=0,record_key="number")
        defaults.update(options)
        return plan_template_batch(self.template,{"member":"Name","number":"ID"},self.records,**defaults)
    def error(self,code,call,*args,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught: call(*args,**kwargs)
        self.assertEqual(caught.exception.code,code); self.assertNotIn("secret",str(caught.exception))
        return caught.exception
    def test_manifest_is_plain_json_signed_and_does_not_edit_source(self):
        json.dumps(self.template)
        self.assertEqual(self.template["nodes"][0]["name"],"Template")
        self.assertEqual(self.source.Pages.Count,1)
        self.assertEqual((self.source.Unit,self.source.ReferencePoint),(3,9))
        self.assertEqual(self.app.outputs,[])
    def test_plan_preserves_leading_zeros_and_materializes_partial_last_sheet(self):
        plan=self.plan(copies_per_record=2)
        self.assertEqual(plan["summary"]["item_count"],6); self.assertEqual(plan["summary"]["sheet_count"],3)
        self.assertEqual([p["record_index"] for p in plan["placements"]],[1,1,2,2,3,3])
        self.assertEqual(plan["request"]["records"][0]["number"],"001")
        self.assertEqual(self.plan()["summary"]["sheet_count"],2)
    def test_native_batch_creates_independent_editable_output_and_preserves_source(self):
        plan=self.plan(); result=self.bridge.execute_template_batch(plan,plan["fingerprint"])
        output=self.bridge.target_doc
        self.assertIsNot(output,self.source); self.assertEqual(output.Pages.Count,2)
        self.assertTrue(result["fit_checks_passed"]); self.assertEqual(result["item_count"],3)
        self.assertEqual(self.root.Shapes.Item(2).Text.Story.Text,"NAME")
        self.assertEqual(self.source.Pages.Count,1)
        self.assertTrue(all(item["object_reference"] is not None for item in result["items"]))
        for item,record in zip(result["items"],self.records):
            matches=self.bridge.find_objects(text_contains=record["member"])["matches"]
            self.assertEqual(len(matches),1)
            self.assertEqual(matches[0]["group_depth"],1)
    def test_missing_fields_duplicate_keys_and_unmapped_targets_fail_before_creation(self):
        for records in ([{"member":"A"}],[self.records[0],self.records[0]]):
            self.error(ErrorCode.INVALID_ARGUMENT,plan_template_batch,self.template,{"member":"Name","number":"ID"},records,record_key="number")
        self.error(ErrorCode.INVALID_ARGUMENT,plan_template_batch,self.template,{"member":"Absent"},self.records)
        self.assertFalse(self.app.outputs)
    def test_duplicate_policy_and_unused_columns_are_explicit(self):
        records=[{**self.records[0],"unused":"X"},{**self.records[0],"unused":"Y"}]
        plan=plan_template_batch(self.template,{"member":"Name","number":"ID"},records,duplicate_policy="allow")
        self.assertEqual(plan["summary"]["unused_columns"],["unused"])
        self.assertEqual(len(plan["summary"]["duplicate_rows"]),1)
    def test_modified_plan_or_source_are_refused_before_copying(self):
        plan=self.plan(); changed=copy.deepcopy(plan); changed["placements"][0]["x"]+=1
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.execute_template_batch,changed,plan["fingerprint"])
        self.root.Shapes.Item(2).Text.Story.Text="Changed"
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertFalse(self.app.outputs)
    def test_replacement_and_foreign_bridge_references_are_refused(self):
        plan=self.plan(); replacement=self.root.clone(self.root.Layer)
        self.root.Layer.Shapes.items=[replacement]; self.root.Page.Shapes.items=[replacement]
        self.error(ErrorCode.OBJECT_NOT_FOUND,self.bridge.execute_template_batch,plan,plan["fingerprint"])
    def test_overflow_policy_discards_owned_output_or_reports_limited_fit(self):
        self.records[0]["member"]="X"*100
        plan=self.plan()
        error=self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(error.details["rollback"]["verified"]); self.assertTrue(self.app.outputs[-1].closed)
        self.assertIs(self.bridge.target_doc,self.source)
        plan=self.plan(overflow_policy="report")
        result=self.bridge.execute_template_batch(plan,plan["fingerprint"])
        self.assertFalse(result["fit_checks_passed"]); self.assertGreater(result["fit_issue_count"],0)
    def test_declared_artistic_field_region_checks_use_relative_inches(self):
        plan=self.plan(field_regions={"member":{"x":.2,"y":1,"width":.1,"height":.3}})
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(self.app.outputs[-1].closed)
    def test_partial_failure_rollback_is_verified_and_never_closes_source(self):
        self.records[1]["member"]="FAIL"; self.app.fail_text="FAIL"
        plan=self.plan()
        error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(error.details["rollback"]["verified"])
        self.assertFalse(self.source.closed); self.assertIs(self.app.ActiveDocument,self.other)
    def test_cleanup_failure_quarantines_the_worker(self):
        self.records[1]["member"]="FAIL"; self.app.fail_text="FAIL"; self.app.fail_close=True
        plan=self.plan()
        with patch.object(server,"CorelBridge",return_value=self.bridge): dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,"dispatcher",dispatcher):
                failed=server.execute_template_batch(plan,plan["fingerprint"])
                self.assertFalse(failed["error"]["details"]["rollback"]["verified"])
                self.assertEqual(server.rotate_object(20,object_name="Template")["error"]["code"],"RECOVERY_REQUIRED")
        finally: dispatcher.close()
    def test_existing_factory_result_is_never_discarded(self):
        self.app.return_existing=True; plan=self.plan()
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertFalse(self.source.closed); self.assertFalse(self.app.outputs)
    def test_foreign_paste_is_refused_before_editing_source(self):
        def foreign_paste(layer):
            layer.Shapes.items.append(self.root)
            return self.root
        plan=self.plan()
        with patch.object(Layer,"Paste",foreign_paste):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(error.details["rollback"]["verified"])
        self.assertEqual(self.root.Name,"Template")
        self.assertEqual(self.root.Shapes.Item(2).Text.Story.Text,"NAME")
    def test_reused_native_duplicate_is_refused(self):
        def reused(shape,x,y):
            shape.Layer.Shapes.items.append(shape); shape.Page.Shapes.items.append(shape)
            return shape
        plan=self.plan()
        with patch.object(TemplateShape,"Duplicate",reused):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(error.details["rollback"]["verified"])
    def test_final_readback_detects_shared_stories_between_rows(self):
        duplicate=TemplateShape.Duplicate
        def shared(shape,x,y):
            result=duplicate(shape,x,y)
            result.Shapes.Item(2).Text.Story=shape.Shapes.Item(2).Text.Story
            return result
        plan=self.plan()
        with patch.object(TemplateShape,"Duplicate",shared):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(error.details["rollback"]["verified"])
        self.assertTrue(self.app.outputs[-1].closed)
    def test_static_copy_geometry_is_verified(self):
        paste=Layer.Paste
        def changed(layer):
            result=paste(layer); result.Shapes.Item(1).width=2
            return result
        plan=self.plan()
        with patch.object(Layer,"Paste",changed):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(error.details["rollback"]["verified"])
    def test_native_page_dimensions_are_read_back(self):
        plan=self.plan()
        with patch.object(Page,"SetSize",lambda page,w,h: None):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertTrue(error.details["rollback"]["verified"])
        self.assertIsNone(self.app.clipboard)
    def test_close_without_membership_change_is_unverified_cleanup(self):
        self.records[1]["member"]="FAIL"; self.app.fail_text="FAIL"; plan=self.plan()
        with patch.object(Document,"Close",lambda doc: None):
            error=self.error(ErrorCode.COREL_COM_ERROR,self.bridge.execute_template_batch,plan,plan["fingerprint"])
        self.assertFalse(error.details["rollback"]["verified"])
        self.assertIn(self.app.outputs[-1],self.app.Documents.items)
    def test_source_nonactive_page_and_observations_are_preserved(self):
        self.source.AddPagesEx(1,8.5,11)
        saved_page=self.source.Pages.Item(2); saved_page.Activate()
        copy_method=TemplateShape.Copy
        def require_active_page(shape):
            self.assertIs(self.app.ActiveDocument.ActivePage,shape.Page)
            copy_method(shape)
        plan=self.plan()
        with patch.object(TemplateShape,"Copy",require_active_page):
            result=self.bridge.execute_template_batch(plan,plan["fingerprint"])
        self.assertTrue(result["source_preservation"]["verified"])
        self.assertIs(self.source.ActivePage,saved_page)
    def test_malformed_style_is_refused_during_planning(self):
        template=copy.deepcopy(self.template)
        template["nodes"][2]["text"]["style"]["size_points"]=True
        template=seal({k:v for k,v in template.items() if k!="fingerprint"})
        self.error(ErrorCode.INVALID_ARGUMENT,plan_template_batch,template,{"member":"Name"},self.records)
        self.assertFalse(self.app.outputs)
    def test_linked_and_fitted_stories_are_refused(self):
        field=self.root.Shapes.Item(2)
        field.Text.Frames=Collection(object(),object())
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE,self.bridge.inspect_text_template,object_name="Template")
        field.Text.Frames=Collection(object()); field.Text.Type=2
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE,self.bridge.inspect_text_template,object_name="Template")
    def test_literal_csv_headers_rows_bom_and_multiline_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"members.csv"
            path.write_bytes(b'\xef\xbb\xbfmember,number\r\n"Line1\nLine2",001\r\n"=1+2",002\r\n')
            data=read_template_csv(str(path))
            self.assertEqual(data["records"][0]["number"],"001")
            self.assertEqual(data["records"][0]["member"],"Line1\nLine2")
            self.assertEqual(data["records"][1]["member"],"=1+2")
            self.assertEqual(data["source_lines"],[2,4])
    def test_bad_csv_is_complete_failure_without_partial_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"bad.csv"
            for text in ("name,name\nA,B\n","name,id\nA\n","name,id\nA,1,extra\n","name,id\n","name,id\n\n","name,id\n\"unclosed,1"):
                path.write_text(text,encoding="utf-8")
                self.error(ErrorCode.INVALID_ARGUMENT,read_template_csv,str(path))
    def test_native_result_schemas_are_strict(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/"catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        tools={t["name"]:t for t in registry["tools"]}; plan=self.plan()
        values={"inspect_text_template":self.bridge.inspect_text_template(object_name="Template"),"plan_template_batch":plan,
                "execute_template_batch":self.bridge.execute_template_batch(plan,plan["fingerprint"])}
        for name,value in values.items():
            validator=Draft202012Validator({"schema_definitions":registry["schema_definitions"],**tools[name]["output_schema"]})
            validator.validate(success_result(name,value,1))
            bad=copy.deepcopy(value); bad["unknown"]=True
            with self.assertRaises(ValidationError): validator.validate(success_result(name,bad,1))


if __name__=="__main__": unittest.main()
