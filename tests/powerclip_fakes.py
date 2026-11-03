"""Independent scene graph model for grouping, clipping, fitting and extraction."""
import copy
from types import SimpleNamespace

from vector_fakes import Shape as VectorShape,Curve,rectangle
from test_layout import Collection
from test_template_jobs import App as BaseApp,Document,Layer as BaseLayer


class Shape(VectorShape):
    def __init__(self,layer,paths=None,name='Shape',code=3):
        super().__init__(layer,Curve.from_paths(layer.Page.document.app,paths or [rectangle()]),name,code)
        self.Shapes=Collection(); self.PowerClip=None; self.clip_owner=None
        self.Bitmap=SimpleNamespace(SizeWidth=600,SizeHeight=300,ResolutionX=300,ResolutionY=300)
        self.Text=SimpleNamespace(Type=0,Frames=Collection(object()),Story=SimpleNamespace(Text='Editable artwork',Font='Arial',Size=18.,Bold=-1))
        self.Transparency=SimpleNamespace(Type=0)
    @property
    def siblings(self):
        if self.clip_owner is not None: return self.clip_owner.PowerClip.Shapes.items
        return self.ParentGroup.Shapes.items if self.ParentGroup is not None else self.Layer.Shapes.items
    def bounds(self):
        if self.Type==7 and self.Shapes.Count:
            bounds=[s.bounds() for s in self.Shapes.items]
            x=min(b[0] for b in bounds); y=min(b[1] for b in bounds)
            return x,y,max(b[0]+b[2] for b in bounds)-x,max(b[1]+b[3] for b in bounds)-y
        return super().bounds()
    def affine(self,scale,origin,destination):
        def move(x,y): return destination[0]+scale*(x-origin[0]),destination[1]+scale*(y-origin[1])
        if self.Type==7 and self.Shapes.Count:
            for child in self.Shapes.items: child.affine(scale,origin,destination)
        else:
            for path in self.curve.paths:
                for node in path.nodes: node.PositionX,node.PositionY=move(node.PositionX,node.PositionY)
                for segment in path.segments:
                    if segment.Type==1:
                        segment.c1=dict(zip(('x','y'),move(segment.c1['x'],segment.c1['y'])))
                        segment.c2=dict(zip(('x','y'),move(segment.c2['x'],segment.c2['y'])))
            if self.Type==6: self.Text.Story.Size*=scale
        if self.PowerClip is not None and self.PowerClip.ContentsLocked:
            for child in self.PowerClip.Shapes.items: child.affine(scale,origin,destination)
        a,b,c,d,x,y=self.matrix; x,y=move(x,y)
        self.matrix=[scale*a,scale*b,scale*c,scale*d,x,y]
    def SetSize(self,w,h):
        if self.app.ignore_fit: return
        x,y,bw,bh=self.bounds(); self.affine(w/bw,(x,y),(x,y))
        if self.app.corrupt_fit_outline and self.Outline.Type==1: self.Outline.Width+=15
        if self.app.corrupt_fit_text and self.Type==6: self.Text.Story.Size=900
    def SetPosition(self,x,y):
        if self.app.ignore_fit: return
        ox,oy,_,_=self.bounds(); self.affine(1.,(ox,oy),(x,y))
    def attach_group(self,child):
        if child in self.Layer.Shapes.items: self.Layer.Shapes.items.remove(child); self.Page.Shapes.items.remove(child)
        child.ParentGroup=self; self.Shapes.items.append(child)
    def Duplicate(self,x,y):
        if self.app.reuse_duplicate: return self
        duplicate=Shape(self.Layer,[p.data() for p in self.curve.paths],self.Name,self.Type)
        duplicate.curve=self.curve if self.app.share_curve and self.Type==3 else self.curve.clone()
        if self.app.share_other_curve and self.Type==3: duplicate.curve=self.app.other.curve
        duplicate.matrix=list(self.matrix); duplicate.Fill=copy.deepcopy(self.Fill); duplicate.Outline=copy.deepcopy(self.Outline)
        duplicate.Bitmap=copy.deepcopy(self.Bitmap); duplicate.Text=copy.deepcopy(self.Text); duplicate.Transparency=copy.deepcopy(self.Transparency)
        if self.app.share_story and self.Type==6: duplicate.Text.Story=self.Text.Story
        if self.app.rename_copies: duplicate.Name+=' (native copy)'
        for child in self.Shapes.items:
            if self.app.share_duplicate_child: duplicate.Shapes.items.append(child)
            else: duplicate.attach_group(child.Duplicate(0,0))
        if self.PowerClip is not None:
            duplicate.PowerClip=Clip(duplicate); duplicate.PowerClip.ContentsLocked=self.PowerClip.ContentsLocked
            for child in self.PowerClip.Shapes.items:
                cloned=child.Duplicate(0,0)
                duplicate.PowerClip.attach(cloned)
        self.app.duplicates.append(duplicate)
        if self.app.detach_duplicate:
            duplicate.Layer.Shapes.items.remove(duplicate); duplicate.Page.Shapes.items.remove(duplicate)
        return duplicate
    def AddToPowerClip(self,frame,center):
        self.app.calls.append(('clip',self,frame,center))
        if self.app.clip_failure: raise RuntimeError('Private C:/secret/source.cdr')
        if self.app.ignore_clip: return
        if frame.PowerClip is None: frame.PowerClip=Clip(frame)
        frame.PowerClip.attach(self)
        if self.app.force_center or center!=0:
            x,y,w,h=frame.bounds(); _,_,cw,ch=self.bounds(); self.SetPosition(x+(w-cw)/2,y+(h-ch)/2)
        if self.app.mutate_original: self.app.original.curve.paths[0].nodes[0].PositionX+=.1
        if self.app.extra_output: Shape(self.Layer,[rectangle(20,20)],'UnknownExtra')
    def Delete(self):
        if self.app.fail_delete: raise RuntimeError('Private C:/secret/source.cdr')
        for child in list(self.Shapes.items): child.Delete()
        if self.PowerClip is not None:
            for child in list(self.PowerClip.Shapes.items): child.Delete()
        if self.ParentGroup is not None: self.ParentGroup.Shapes.items.remove(self)
        elif self.clip_owner is not None: self.clip_owner.PowerClip.Shapes.items.remove(self)
        else:
            self.Layer.Shapes.items.remove(self); self.Page.Shapes.items.remove(self)


class Clip:
    def __init__(self,parent): self.Parent=parent; self.Shapes=Collection(); self.ContentsLocked=False
    def attach(self,shape):
        shape.Layer.Shapes.items.remove(shape); shape.Page.Shapes.items.remove(shape)
        shape.clip_owner=self.Parent; self.Shapes.items.append(shape)
    def ExtractShapes(self):
        app=self.Parent.app
        if app.extract_failure: raise RuntimeError('Private C:/secret/source.cdr')
        children=list(self.Shapes.items)
        if app.ignore_extract: return Collection(*children)
        self.Shapes.items=[]
        for shape in children:
            shape.clip_owner=None; shape.Layer.Shapes.items.append(shape); shape.Page.Shapes.items.append(shape)
        if app.corrupt_extract: children[0].curve.paths[0].nodes[0].PositionX+=.1
        if app.alias_extract: return Collection(app.original)
        return Collection(*reversed(children)) if app.reverse_extract else Collection(*children)


class Range(Collection):
    def Add(self,shape): self.items.append(shape)
    def Group(self):
        group=Shape(self.items[0].Layer,name='CopiedGroup',code=7)
        children=list(reversed(self.items)) if group.app.reverse_group else self.items
        for child in children: group.attach_group(child)
        return group


class App(BaseApp):
    def __init__(self):
        super().__init__(); self.duplicates=[]; self.calls=[]
        self.reuse_duplicate=False; self.share_curve=False; self.share_other_curve=False; self.share_duplicate_child=False
        self.share_story=False
        self.rename_copies=False
        self.detach_duplicate=False
        self.corrupt_fit_outline=False; self.corrupt_fit_text=False
        self.ignore_fit=False; self.clip_failure=False; self.ignore_clip=False; self.force_center=False; self.extra_output=False
        self.mutate_original=False; self.fail_delete=False; self.extract_failure=False; self.ignore_extract=False
        self.corrupt_extract=False; self.alias_extract=False; self.reverse_extract=False; self.reverse_group=False
    def CreateShapeRange(self): return Range()


def fixture():
    app=App(); document=Document(app,'ClipSource.cdr'); app.Documents.items=[document]; app.ActiveDocument=document
    layer=BaseLayer(document.ActivePage,'ClipLayer'); document.ActivePage.AllLayers.items.append(layer); layer.Activate()
    frame=Shape(layer,[rectangle(1,1,4,4)],'Frame',1)
    artwork=Shape(layer,[rectangle(0,0,4,2)],'Artwork',3)
    app.original=frame
    return app,document,layer,frame,artwork
