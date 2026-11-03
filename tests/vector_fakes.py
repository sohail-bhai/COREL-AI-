"""Independent in-memory model of the X7 curve/ownership interfaces used by tests."""
import copy
import math
from types import SimpleNamespace
from test_layout import Collection,Shape as BaseShape
from test_template_jobs import App as BaseApp,Document,Layer as BaseLayer


def rectangle(x=0,y=0,w=2,h=2):
    return {'start':{'x':x,'y':y},'closed':True,'segments':[
        {'type':'line','end':{'x':x+w,'y':y}}, {'type':'line','end':{'x':x+w,'y':y+h}},
        {'type':'line','end':{'x':x,'y':y+h}}, {'type':'line','end':{'x':x,'y':y}}]}


class Node:
    def __init__(self,subpath,x,y): self.SubPath=subpath; self.PositionX=x; self.PositionY=y; self.Type=0
    def SetPosition(self,x,y):
        if self.SubPath.app.ignore_move: return
        dx,dy=x-self.PositionX,y-self.PositionY
        for segment in self.SubPath.segments:
            if segment.Type==1:
                if segment.StartNode is self: segment.c1={'x':segment.c1['x']+dx,'y':segment.c1['y']+dy}
                if segment.EndNode is self: segment.c2={'x':segment.c2['x']+dx,'y':segment.c2['y']+dy}
        self.PositionX,self.PositionY=x,y


class Segment:
    def __init__(self,subpath,start,end,c1=None,c2=None):
        self.SubPath=subpath; self.StartNode=start; self.EndNode=end; self.Type=1 if c1 is not None else 0
        self.c1,self.c2=copy.deepcopy(c1),copy.deepcopy(c2)
    @property
    def StartingControlPointX(self): return self.c1['x']
    @property
    def StartingControlPointY(self): return self.c1['y']
    @property
    def EndingControlPointX(self): return self.c2['x']
    @property
    def EndingControlPointY(self): return self.c2['y']
    def SetStartingControlPointPosition(self,x,y): self.c1={'x':x,'y':y}
    def SetEndingControlPointPosition(self,x,y): self.c2={'x':x,'y':y}


class SubPath:
    def __init__(self,app,x,y): self.app=app; self.nodes=[Node(self,x,y)]; self.segments=[]; self.closed=False
    @property
    def Nodes(self): return Collection(*self.nodes)
    @property
    def Segments(self): return Collection(*self.segments)
    @property
    def Closed(self): return self.closed
    @Closed.setter
    def Closed(self,value):
        if value and not self.closed:
            first,last=self.nodes[0],self.nodes[-1]
            if (first.PositionX,first.PositionY)!=(last.PositionX,last.PositionY): self.AppendLineSegment(first.PositionX,first.PositionY)
            self.segments[-1].EndNode=first; self.nodes.pop()
        self.closed=value
    def AppendLineSegment(self,x,y):
        end=Node(self,x,y); segment=Segment(self,self.nodes[-1],end)
        self.nodes.append(end); self.segments.append(segment); return segment
    def AppendCurveSegment2(self,x,y,c1x,c1y,c2x,c2y):
        end=Node(self,x,y); segment=Segment(self,self.nodes[-1],end,{'x':c1x,'y':c1y},{'x':c2x,'y':c2y})
        self.nodes.append(end); self.segments.append(segment); return segment
    def data(self):
        return {'start':{'x':self.nodes[0].PositionX,'y':self.nodes[0].PositionY},'closed':self.Closed,
            'segments':[{'type':'cubic' if s.Type==1 else 'line','end':{'x':s.EndNode.PositionX,'y':s.EndNode.PositionY},
                **({'control1':dict(s.c1),'control2':dict(s.c2)} if s.Type==1 else {})} for s in self.segments]}


class Curve:
    def __init__(self,app): self.app=app; self.paths=[]
    @property
    def SubPaths(self): return Collection(*self.paths)
    @property
    def Nodes(self): return Collection(*[node for path in self.paths for node in path.nodes])
    @property
    def Segments(self): return Collection(*[segment for path in self.paths for segment in path.segments])
    def CreateSubPath(self,x,y):
        path=SubPath(self.app,x,y); self.paths.append(path); return path
    @classmethod
    def from_paths(cls,app,paths):
        curve=cls(app)
        for path in paths:
            native=curve.CreateSubPath(path['start']['x'],path['start']['y'])
            for segment in path['segments']:
                end=segment['end']
                if segment['type']=='line': native.AppendLineSegment(end['x'],end['y'])
                else: native.AppendCurveSegment2(end['x'],end['y'],segment['control1']['x'],segment['control1']['y'],segment['control2']['x'],segment['control2']['y'])
            native.Closed=path['closed']
        return curve
    def clone(self):
        result=Curve.from_paths(self.app,[p.data() for p in self.paths])
        for original,cloned in zip(self.paths,result.paths):
            for a,b in zip(original.nodes,cloned.nodes): b.Type=a.Type
        return result


def bezier(p0,p1,p2,p3,t): return (1-t)**3*p0+3*(1-t)**2*t*p1+3*(1-t)*t*t*p2+t**3*p3


class Shape(BaseShape):
    def __init__(self,layer,curve,name='Vector',code=3):
        app=layer.Page.document.app
        super().__init__(name,app.next_id,0,0,0,0); app.next_id+=1
        self.app=app; self.Layer=layer; self.Page=layer.Page; self.Type=code; self.curve=curve
        self.Fill=SimpleNamespace(Type=0); self.Outline=SimpleNamespace(Type=0,Width=0.)
        layer.Shapes.items.append(self); self.Page.Shapes.items.append(self)
    @property
    def Curve(self):
        if self.Type!=3: raise RuntimeError('Primitive shapes require DisplayCurve')
        return self.curve
    @property
    def DisplayCurve(self): return self.curve
    def bounds(self):
        points=[]
        for path in self.curve.paths:
            for segment in path.segments:
                start=(segment.StartNode.PositionX,segment.StartNode.PositionY); end=(segment.EndNode.PositionX,segment.EndNode.PositionY)
                points.extend((start,end))
                if segment.Type==1:
                    controls=((segment.c1['x'],segment.c1['y']),(segment.c2['x'],segment.c2['y']))
                    roots=set()
                    for dimension in (0,1):
                        p0,p1,p2,p3=start[dimension],controls[0][dimension],controls[1][dimension],end[dimension]
                        a=-p0+3*p1-3*p2+p3; b=2*(p0-2*p1+p2); c=p1-p0
                        if abs(a)<1e-12:
                            if abs(b)>1e-12: roots.add(-c/b)
                        elif b*b-4*a*c>=0:
                            d=math.sqrt(b*b-4*a*c); roots.update(((-b+d)/(2*a),(-b-d)/(2*a)))
                    for t in roots:
                        if 0<t<1: points.append(tuple(bezier(start[i],controls[0][i],controls[1][i],end[i],t) for i in (0,1)))
        xs,ys=zip(*points); return min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)
    def Duplicate(self,x,y):
        if self.app.reuse_duplicate: return self
        result=Shape(self.Layer,self.curve if self.app.share_curve else self.curve.clone(),self.Name,self.Type)
        result.Fill=copy.deepcopy(self.Fill); result.Outline=copy.deepcopy(self.Outline)
        self.app.duplicates.append(result); return result
    def Delete(self):
        if self.app.fail_delete: raise RuntimeError('Private C:/secret/source.cdr')
        self.Layer.Shapes.items.remove(self); self.Page.Shapes.items.remove(self)
    def ConvertToCurves(self): self.Type=3
    def _boolean(self,other,operation,leave_source,leave_target):
        self.app.calls.append((operation,self,other,leave_source,leave_target))
        if self.app.boolean_failure: raise RuntimeError('Private C:/secret/source.cdr')
        if self.app.mutate_original: self.app.original.curve.paths[0].nodes[0].PositionX+=.1
        ax,ay,aw,ah=self.bounds(); bx,by,bw,bh=other.bounds()
        if operation=='weld': x,y,x2,y2=min(ax,bx),min(ay,by),max(ax+aw,bx+bw),max(ay+ah,by+bh)
        elif operation=='intersect': x,y,x2,y2=max(ax,bx),max(ay,by),min(ax+aw,bx+bw),min(ay+ah,by+bh)
        else: x,y,x2,y2=max(bx,ax+aw),by,bx+bw,by+bh
        if x2<=x or y2<=y: return None
        result=Shape(self.Layer,Curve.from_paths(self.app,[rectangle(x,y,x2-x,y2-y)]))
        if self.app.extra_output: Shape(self.Layer,Curve.from_paths(self.app,[rectangle(20,20)]),'UnknownExtra')
        return result
    def Weld(self,other,a,b): return self._boolean(other,'weld',a,b)
    def Trim(self,other,a,b): return self._boolean(other,'trim',a,b)
    def Intersect(self,other,a,b): return self._boolean(other,'intersect',a,b)
    def BreakApartEx(self):
        result=[Shape(self.Layer,Curve.from_paths(self.app,[p.data()])) for p in reversed(self.curve.paths)]
        self.Delete(); return Collection(*result)


class Layer(BaseLayer):
    def CreateCurve(self,curve):
        if self.Page.document.app.return_existing_shape: return self.Page.document.app.original
        return Shape(self,curve)


class Range(Collection):
    def Add(self,shape): self.items.append(shape)
    def Combine(self):
        layer=self.items[0].Layer; app=layer.Page.document.app
        paths=[path.data() for shape in reversed(self.items) for path in shape.curve.paths]
        if app.corrupt_combined: paths.pop()
        result=Shape(layer,Curve.from_paths(app,paths))
        for shape in self.items: shape.Delete()
        return result


class App(BaseApp):
    def __init__(self):
        super().__init__(); self.ignore_move=False; self.reuse_duplicate=False; self.share_curve=False; self.fail_delete=False
        self.boolean_failure=False; self.mutate_original=False; self.extra_output=False; self.corrupt_combined=False
        self.return_existing_shape=False; self.calls=[]; self.duplicates=[]
    def CreateCurve(self,document): return Curve(self)
    def CreateShapeRange(self): return Range()


def fixture():
    app=App(); document=Document(app,'Source.cdr'); app.Documents.items=[document]; app.ActiveDocument=document
    layer=Layer(document.ActivePage,'Vectors'); document.ActivePage.AllLayers.items.append(layer); layer.Activate()
    return app,document,layer
