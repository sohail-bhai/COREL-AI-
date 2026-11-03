from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from jsonschema import Draft202012Validator, ValidationError

from corel_operator import server
from corel_operator.corel_bridge import CorelBridge
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.layout import plan_distribution
from corel_operator.results import success_result
from fake_documents import attach_open_document


class Collection:
    def __init__(self,*items):
        self.items=list(items)
    @property
    def Count(self):
        return len(self.items)
    def Item(self,index):
        return self.items[index-1]


class Shape:
    def __init__(self,name,static_id,x,y,width,height):
        self.Name,self.StaticID,self.Type=name,static_id,1
        self.width,self.height=width,height
        self.matrix=[1.,0.,0.,1.,x,y]
        self.ParentGroup=None
        self.writes=[]
        self.fail_on=None
        self.noop=False
    def bounds(self):
        a,b,c,d,x,y=self.matrix
        points=[(a*u+c*v+x,b*u+d*v+y) for u,v in ((0,0),(self.width,0),(0,self.height),(self.width,self.height))]
        xs,ys=[p[0] for p in points],[p[1] for p in points]
        return min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)
    @property
    def PositionX(self): return self.bounds()[0]
    @property
    def PositionY(self): return self.bounds()[1]
    @property
    def SizeWidth(self): return self.bounds()[2]
    @property
    def SizeHeight(self): return self.bounds()[3]
    @property
    def RotationAngle(self): return math.degrees(math.atan2(self.matrix[1],self.matrix[0])) % 360
    @property
    def siblings(self): return (self.ParentGroup.Shapes if self.ParentGroup is not None else self.Layer.Shapes).items
    @property
    def ZOrder(self): return 100+self.siblings.index(self)  # deliberately opaque native value
    def GetMatrix(self): return tuple(self.matrix)
    def error(self,operation):
        if self.fail_on==operation:
            raise RuntimeError("Private content C:/client/secret.cdr")
    def RotateEx(self,angle,cx,cy):
        self.writes.append(("rotate",angle,cx,cy))
        if not self.noop:
            co,si=math.cos(math.radians(angle)),math.sin(math.radians(angle))
            a,b,c,d,x,y=self.matrix
            self.matrix=[co*a-si*b,si*a+co*b,co*c-si*d,si*c+co*d,
                         cx+co*(x-cx)-si*(y-cy),cy+si*(x-cx)+co*(y-cy)]
        self.error("rotate")
    def Flip(self,axes):
        self.writes.append(("flip",axes))
        if not self.noop:
            x,y,w,h=self.bounds()
            if axes&1:
                self.matrix[0]*=-1; self.matrix[2]*=-1; self.matrix[4]=2*(x+w/2)-self.matrix[4]
            if axes&2:
                self.matrix[1]*=-1; self.matrix[3]*=-1; self.matrix[5]=2*(y+h/2)-self.matrix[5]
        self.error("flip")
    def SetPosition(self,x,y):
        self.writes.append(("position",x,y))
        if not self.noop:
            self.matrix[4]+=x-self.PositionX
            self.matrix[5]+=y-self.PositionY
        self.error("position")
    def OrderIsInFrontOf(self,other): return self.siblings.index(self)<self.siblings.index(other)
    def order(self,position):
        self.writes.append(("order",position))
        items=self.siblings
        index=items.index(self)
        target={"front":0,"back":len(items)-1,"forward_one":max(0,index-1),"back_one":min(len(items)-1,index+1)}[position]
        if not self.noop:
            items.remove(self); items.insert(target,self)
        self.error("order")
    def OrderToFront(self): self.order("front")
    def OrderToBack(self): self.order("back")
    def OrderForwardOne(self): self.order("forward_one")
    def OrderBackOne(self): self.order("back_one")


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.a=Shape("A",101,0.,1.,1.,1.)
        self.b=Shape("B",102,4.,3.,2.,1.)
        self.c=Shape("C",103,10.,6.,1.,1.)
        self.shapes=[self.a,self.b,self.c]
        self.layer=SimpleNamespace(Name="Artwork",Shapes=Collection(*self.shapes))
        self.page=SimpleNamespace(Index=1,Shapes=Collection(*self.shapes),AllLayers=Collection(self.layer))
        for shape in self.shapes:
            shape.Layer,shape.Page=self.layer,self.page
        self.document=SimpleNamespace(Name="Target.cdr",Pages=Collection(self.page),ActivePage=self.page,Unit=3,ReferencePoint=9,Dirty=False)
        self.bridge=CorelBridge()
        attach_open_document(self.bridge,self.document)

    def error(self,code,function,**kwargs):
        with self.assertRaises(CorelBridgeError) as caught:
            function(**kwargs)
        self.assertEqual(caught.exception.code,code)
        self.assertNotIn("secret",str(caught.exception))

    def refs(self):
        return [self.bridge.get_object_transform(object_name=s.Name)["object"]["object_reference"] for s in self.shapes]

    def test_transform_readback_preserves_context_and_reports_native_matrix(self):
        value=self.bridge.get_object_transform(object_name="B")
        self.assertEqual(value["transform"]["matrix"],[1.,0.,0.,1.,4.,3.])
        self.assertEqual(value["transform"]["native_z_order"],101)
        self.assertEqual((self.document.Unit,self.document.ReferencePoint),(3,9))
        self.assertFalse(self.b.writes)

    def test_rotation_uses_measured_center_and_verifies_actual_orientation(self):
        value=self.bridge.rotate_object(90,object_name="B")
        self.assertEqual(self.b.writes,[("rotate",90,5.,3.5)])
        bounds=value["actual_transform"]["bounds_inches"]
        self.assertAlmostEqual(bounds["x"],4.5)
        self.assertAlmostEqual(bounds["y"],2.5)
        self.assertAlmostEqual(bounds["width"],1)
        self.assertAlmostEqual(bounds["height"],2)
        self.assertEqual((self.document.Unit,self.document.ReferencePoint),(3,9))

    def test_absolute_rotation_wraps_and_external_pivot_changes_position(self):
        self.bridge.rotate_object(350,object_name="A")
        value=self.bridge.rotate_object(370,relative=False,center_x_inches=0,center_y_inches=0,object_name="A")
        self.assertAlmostEqual(value["actual_transform"]["rotation_degrees"],10)
        self.assertAlmostEqual(value["applied_angle_degrees"],-340)
        self.assertEqual(value["center_inches"],{"x":0,"y":0})

    def test_rotate_noop_native_and_partial_failure_require_errors(self):
        self.a.noop=True
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.rotate_object,angle_degrees=90,object_name="A")
        self.a.noop=False; self.a.fail_on="rotate"
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.rotate_object,angle_degrees=90,object_name="A")
        self.assertTrue(self.bridge._operation_mutation_started)

    def test_flip_axes_change_matrix_and_repeated_flip_restores_it(self):
        for axis,code in (("horizontal",1),("vertical",2),("both",3)):
            baseline=self.b.GetMatrix()
            value=self.bridge.flip_object(axis,object_name="B")
            self.assertEqual(self.b.writes[-1],("flip",code))
            self.assertEqual(value["orientation_check"],"native_matrix_parity")
            self.bridge.flip_object(axis,object_name="B")
            for actual,expected in zip(self.b.GetMatrix(),baseline):
                self.assertAlmostEqual(actual,expected)

    def test_mirror_noop_and_degenerate_matrices_are_refused(self):
        self.a.noop=True
        for axis in ("horizontal","both"):
            self.error(ErrorCode.COREL_COM_ERROR,self.bridge.flip_object,axis=axis,object_name="A")
        self.a.matrix[0]=0
        self.error(ErrorCode.UNSUPPORTED_IN_PROFILE,self.bridge.flip_object,axis="horizontal",object_name="A")

    def test_small_matrix_noop_cannot_pass_mirror_parity_tolerance(self):
        self.a.noop=True
        self.a.matrix[0]=1e-10
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.flip_object,axis="horizontal",object_name="A")

    def test_incomplete_or_ambiguous_stacking_scope_is_refused(self):
        self.layer.Shapes.items.append(self.a)
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.order_object,position="front",object_name="B")
        self.layer.Shapes.items.pop()
        with patch.object(self.a,"OrderIsInFrontOf",return_value="yes"):
            self.error(ErrorCode.COREL_COM_ERROR,self.bridge.order_object,position="back",object_name="A")
        self.assertFalse(self.a.writes)

    def test_order_uses_native_relations_instead_of_assuming_zorder_direction(self):
        value=self.bridge.order_object("front",object_name="C")
        self.assertEqual(self.layer.Shapes.items,[self.c,self.a,self.b])
        self.assertEqual(value["before_order"]["rank_from_front"],3)
        self.assertEqual(value["actual_order"]["rank_from_front"],1)
        self.bridge.order_object("back_one",object_name="C")
        self.assertEqual(self.layer.Shapes.items,[self.a,self.c,self.b])
        self.bridge.order_object("back",object_name="A")
        self.assertEqual(self.layer.Shapes.items,[self.c,self.b,self.a])
        self.bridge.order_object("forward_one",object_name="B")
        self.assertEqual(self.layer.Shapes.items,[self.b,self.c,self.a])

    def test_order_at_edge_is_valid_but_native_noop_away_from_edge_is_error(self):
        self.bridge.order_object("forward_one",object_name="A")
        self.a.noop=True
        self.error(ErrorCode.COREL_COM_ERROR,self.bridge.order_object,position="back",object_name="A")

    def test_nested_order_is_scoped_to_immediate_group_siblings(self):
        group=Shape("Group",200,0,0,1,1)
        group.Type=7; group.Shapes=Collection(self.b,self.c)
        group.Layer,group.Page=self.layer,self.page
        self.b.ParentGroup=self.c.ParentGroup=group
        self.layer.Shapes.items=[self.a,group]; self.page.Shapes.items=[self.a,group]
        reference=self.bridge.find_objects(name_contains="C")["matches"][0]["object_reference"]
        value=self.bridge.order_object("front",object_reference=reference)
        self.assertEqual(group.Shapes.items,[self.c,self.b])
        self.assertEqual(value["actual_order"]["sibling_count"],2)
        self.assertEqual(self.layer.Shapes.items,[self.a,group])

    def test_distribution_equal_gaps_and_explicit_spacing_preserve_orthogonal_geometry(self):
        value=self.bridge.distribute_objects("horizontal",object_names=["C","A","B"])
        self.assertEqual(value["spacing_inches"],3.5)
        self.assertEqual([o["object"]["object_name"] for o in value["objects"]],["A","B","C"])
        self.assertAlmostEqual(self.b.PositionX,4.5)
        self.assertEqual((self.b.PositionY,self.b.SizeWidth,self.b.SizeHeight),(3,2,1))
        value=self.bridge.distribute_objects("horizontal",object_names=["A","B","C"],spacing_inches=.5)
        self.assertEqual([s.PositionX for s in self.shapes],[0,1.5,4])
        self.assertEqual(value["spacing_inches"],.5)
        self.assertEqual((self.document.Unit,self.document.ReferencePoint),(3,9))

    def test_distribution_equal_centers_vertical_and_rotated_shapes(self):
        self.bridge.rotate_object(90,object_name="B")
        value=self.bridge.distribute_objects("vertical",object_references=self.refs(),mode="equal_centers")
        centers=[o["actual_transform"]["bounds_inches"]["y"]+o["actual_transform"]["bounds_inches"]["height"]/2 for o in value["objects"]]
        self.assertAlmostEqual(centers[1]-centers[0],centers[2]-centers[1])
        self.assertAlmostEqual(self.b.RotationAngle,90)

    def test_overlap_requires_explicit_choice_and_no_positions_are_written_on_refusal(self):
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.distribute_objects,axis="horizontal",object_names=["A","B","C"],spacing_inches=-.5)
        self.assertFalse(any(shape.writes for shape in self.shapes))
        value=self.bridge.distribute_objects("horizontal",object_names=["A","B","C"],spacing_inches=-.5,allow_overlap=True)
        self.assertTrue(value["has_axis_overlap"])

    def test_distribution_rejects_duplicate_identity_and_group_with_child(self):
        refs=self.refs()
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.distribute_objects,axis="horizontal",object_references=[refs[0],refs[0],refs[1]])
        group=Shape("Group",200,0,0,1,1); group.Type=7; group.Shapes=Collection(self.b)
        group.Layer,group.Page=self.layer,self.page; self.b.ParentGroup=group
        self.layer.Shapes.items=[self.a,group,self.c]; self.page.Shapes.items=[self.a,group,self.c]
        refs=[m["object_reference"] for m in self.bridge.find_objects()["matches"] if m["object_name"] in ("A","Group","B")]
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.distribute_objects,axis="horizontal",object_references=refs)
        self.assertFalse(self.b.writes)

    def test_every_distribution_target_is_preflighted_before_any_move(self):
        refs=self.refs(); bad=copy.deepcopy(refs[2]); bad["static_id"]=999
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.distribute_objects,axis="horizontal",object_references=[refs[0],refs[1],bad])
        self.assertFalse(any(shape.writes for shape in self.shapes))

    def test_partial_distribution_failure_triggers_worker_quarantine(self):
        self.b.fail_on="position"
        with patch.object(server,"CorelBridge",return_value=self.bridge):
            dispatcher=server.CorelDispatcher()
        try:
            with patch.object(server,"dispatcher",dispatcher):
                value=server.distribute_objects("horizontal",object_names=["A","B","C"])
                self.assertEqual(value["error"]["code"],"COREL_COM_ERROR")
                self.assertEqual(server.rotate_object(20,object_name="C")["error"]["code"],"RECOVERY_REQUIRED")
                self.assertTrue(server.get_object_transform(object_name="B")["ok"])
                self.assertFalse(self.c.writes)
        finally:
            dispatcher.close()

    def test_signed_references_survive_reorder_and_refuse_replacement_and_foreign_page(self):
        refs=self.refs()
        self.bridge.order_object("back",object_reference=refs[0])
        self.bridge.rotate_object(90,object_reference=refs[0])
        replacement=copy.copy(self.a); self.layer.Shapes.items[-1]=replacement; self.page.Shapes.items[0]=replacement
        self.error(ErrorCode.OBJECT_NOT_FOUND,self.bridge.flip_object,axis="vertical",object_reference=refs[0])
        other=SimpleNamespace(Index=2,Shapes=Collection(),AllLayers=Collection())
        self.document.Pages.items.append(other); self.document.ActivePage=other
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.rotate_object,angle_degrees=20,object_reference=refs[1])
        self.assertEqual(self.bridge.get_object_transform(object_reference=refs[1])["object"]["page_index"],1)

    def test_unavailable_matrix_and_nonfinite_metadata_fail_explicitly(self):
        for matrix in ((1,2,3),[True,0,0,1,0,0],[float("nan"),0,0,1,0,0]):
            with patch.object(self.a,"GetMatrix",return_value=matrix):
                self.error(ErrorCode.COREL_COM_ERROR,self.bridge.get_object_transform,object_name="A")
        with patch.object(self.a,"RotateEx",None):
            self.error(ErrorCode.UNSUPPORTED_IN_PROFILE,self.bridge.rotate_object,angle_degrees=20,object_name="A")

    def test_invalid_options_and_selectors_are_refused(self):
        for kwargs in ({"angle_degrees":True},{"angle_degrees":float("inf")},{"angle_degrees":20,"relative":1},
                       {"angle_degrees":20,"center_x_inches":1},{"angle_degrees":20,"center_x_inches":0,"center_y_inches":10**400}):
            self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.rotate_object,object_name="A",**kwargs)
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.flip_object,axis="diagonal",object_name="A")
        self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.order_object,position="middle",object_name="A")
        self.error(ErrorCode.AMBIGUOUS_SELECTOR,self.bridge.distribute_objects,axis="horizontal",object_names=["A","B","C"],object_references=[])
        for kwargs in ({"object_names":["A","A","B"]},{"object_names":["A","B"]},{"object_names":["A","B",{}]},
                       {"object_names":["A","B","C"],"allow_overlap":1},{"object_names":["A","B","C"],"mode":"equal_centers","spacing_inches":1}):
            self.error(ErrorCode.INVALID_ARGUMENT,self.bridge.distribute_objects,axis="horizontal",**kwargs)
        self.assertFalse(any(shape.writes for shape in self.shapes))

    def test_plan_preserves_outer_extent_with_protruding_middle_object(self):
        bounds=[dict(x=0,y=0,width=1,height=1),dict(x=2,y=0,width=10,height=1),dict(x=4,y=0,width=1,height=1)]
        value=plan_distribution(bounds,"horizontal",allow_overlap=True)
        last=value["targets"][-1]["bounds"]
        self.assertAlmostEqual(last["x"]+last["width"],12)

    def test_real_results_validate_against_strict_schemas(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/"catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        tools={t["name"]:t for t in registry["tools"]}
        values={"get_object_transform":self.bridge.get_object_transform(object_name="A"),
                "rotate_object":self.bridge.rotate_object(90,object_name="A"),
                "flip_object":self.bridge.flip_object("horizontal",object_name="B"),
                "order_object":self.bridge.order_object("back",object_name="C"),
                "distribute_objects":self.bridge.distribute_objects("horizontal",object_names=["A","B","C"])}
        for name,value in values.items():
            validator=Draft202012Validator({"schema_definitions":registry["schema_definitions"],**tools[name]["output_schema"]})
            validator.validate(success_result(name,value,1))
            bad=copy.deepcopy(value); bad["unexpected"]=True
            with self.assertRaises(ValidationError): validator.validate(success_result(name,bad,1))

    def test_request_schemas_reject_ambiguous_options_and_missing_selectors(self):
        registry=json.loads((Path(__file__).resolve().parents[1]/"catalog/mcp_tool_registry.json").read_text(encoding="utf-8"))
        tools={t["name"]:t for t in registry["tools"]}
        rotation=Draft202012Validator({"schema_definitions":registry["schema_definitions"],**tools["rotate_object"]["input_schema"]})
        rotation.validate({"angle_degrees":30,"object_name":"A"})
        rotation.validate({"angle_degrees":30,"shape_index":1,"center_x_inches":0,"center_y_inches":0})
        for bad in ({"angle_degrees":30},{"angle_degrees":True,"object_name":"A"},
                    {"angle_degrees":30,"object_name":"A","center_x_inches":0},
                    {"angle_degrees":30,"object_name":"A","shape_index":1},
                    {"angle_degrees":30,"object_name":"A","unexpected":1}):
            with self.assertRaises(ValidationError): rotation.validate(bad)
        distribution=Draft202012Validator({"schema_definitions":registry["schema_definitions"],**tools["distribute_objects"]["input_schema"]})
        distribution.validate({"axis":"horizontal","object_names":["A","B","C"],"object_references":None})
        distribution.validate({"axis":"vertical","object_references":self.refs()})
        for bad in ({"axis":"horizontal"},{"axis":"horizontal","object_names":["A","B"]},
                    {"axis":"horizontal","object_names":["A","A","B"]},
                    {"axis":"horizontal","object_names":["A","B","C"],"object_references":self.refs()},
                    {"axis":"horizontal","object_names":["A","B","C"],"mode":"equal_centers","spacing_inches":1}):
            with self.assertRaises(ValidationError): distribution.validate(bad)

    def test_server_forwards_layout_options(self):
        with patch.object(server,"_tool",return_value={}) as call:
            server.rotate_object(90,relative=False,object_name="A")
            self.assertEqual(call.call_args.args,("rotate_object","rotate_object",90,False,None,None,"A",0,None))
            server.distribute_objects("horizontal",object_names=["A","B","C"])
            self.assertEqual(call.call_args.args,("distribute_objects","distribute_objects","horizontal",["A","B","C"],None,"equal_gaps",None,False))


if __name__=="__main__":
    unittest.main()
