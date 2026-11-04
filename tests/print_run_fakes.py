"""Independent copy/transform scene model for the native print run contract."""
import copy
import math
from types import SimpleNamespace

from test_layout import Collection
from test_template_jobs import App as BaseApp, Document as BaseDocument, Page as BasePage, Layer as BaseLayer
from powerclip_fakes import Shape as BaseShape, Clip, rectangle
from corel_operator.corel_bridge import CorelBridge


class Layer(BaseLayer):
    def __init__(self, page, name):
        super().__init__(page, name)
        self.Visible = self.Editable = self.Printable = True
        self.Master = self.IsSpecialLayer = False
    def Paste(self):
        app = self.Page.document.app
        if app.fail_paste: raise RuntimeError('Private source path')
        return app.clipboard.clone(self)


class Page(BasePage):
    def __init__(self, document, index):
        self.Name = f'Sheet {index}'
        super().__init__(document, index)
        self.Layers = self.AllLayers
    def CreateLayer(self, name):
        layer = Layer(self, name); self.AllLayers.items.append(layer); return layer


class Document(BaseDocument):
    def __init__(self, app, name, owned=False):
        super().__init__(app, name, owned)
        self.Pages = Collection(Page(self, 1)); self.ActivePage = self.Pages.Item(1)
        self.MasterPage = SimpleNamespace(Layers=Collection(), Shapes=Collection())
        self.SelectionRange = Collection()
    def AddPagesEx(self, count, width, height):
        for _ in range(count):
            page = Page(self, self.Pages.Count+1); page.SetSize(width, height); self.Pages.items.append(page)


class Shape(BaseShape):
    def __init__(self, layer, paths=None, name='Repeat', code=3):
        super().__init__(layer, paths, name, code)
        self.Effects = Collection()
    def Copy(self): self.app.clipboard = self
    def clone(self, layer):
        cloned = Shape(layer, [p.data() for p in self.curve.paths], self.Name, self.Type)
        cloned.matrix = list(self.matrix)
        for field in ('Fill', 'Outline', 'Text', 'Bitmap', 'Transparency'):
            setattr(cloned, field, copy.deepcopy(getattr(self, field)))
        for child in self.Shapes.items: cloned.attach_group(child.clone(layer))
        if self.PowerClip is not None:
            cloned.PowerClip = Clip(cloned); cloned.PowerClip.ContentsLocked = self.PowerClip.ContentsLocked
            for child in self.PowerClip.Shapes.items: cloned.PowerClip.attach(child.clone(layer))
        return cloned
    def Duplicate(self, x, y):
        if self.app.reuse_duplicate: return self
        return self.clone(self.Layer)
    def SetPosition(self, x, y):
        if self.app.ignore_fit: return
        super().SetPosition(x, y)
        if self.app.corrupt_prior and self.app.outputs:
            first = self.app.outputs[0].Pages.Item(1).ActiveLayer.Shapes.items[0]
            if first is not self: first.curve.paths[0].nodes[0].PositionX += .01
    def RotateEx(self, angle, cx, cy):
        if self.app.ignore_rotate: return
        theta = math.radians(angle); a = math.cos(theta); b = math.sin(theta)
        def point(x, y): return cx+a*(x-cx)-b*(y-cy), cy+b*(x-cx)+a*(y-cy)
        def visit(shape):
            for path in shape.curve.paths:
                for node in path.nodes: node.PositionX, node.PositionY = point(node.PositionX, node.PositionY)
                for segment in path.segments:
                    if segment.Type == 1:
                        segment.c1 = dict(zip(('x', 'y'), point(segment.c1['x'], segment.c1['y'])))
                        segment.c2 = dict(zip(('x', 'y'), point(segment.c2['x'], segment.c2['y'])))
            for child in shape.Shapes.items: visit(child)
            if shape.PowerClip is not None and shape.PowerClip.ContentsLocked:
                for child in shape.PowerClip.Shapes.items: visit(child)
            p, q, r, s, x, y = shape.matrix; x, y = point(x, y)
            shape.matrix = [a*p-b*q, b*p+a*q, a*r-b*s, b*r+a*s, x, y]
        visit(self)


class App(BaseApp):
    def __init__(self):
        super().__init__()
        self.fail_paste = self.reuse_duplicate = self.ignore_rotate = self.ignore_fit = self.corrupt_prior = False
    def CreateDocument(self):
        if self.return_existing: return self.Documents.Item(1)
        document = Document(self, 'Print output', True)
        self.Documents.items.append(document); self.outputs.append(document); self.ActiveDocument = document
        return document


def fixture():
    app = App(); source = Document(app, 'Source.cdr'); other = Document(app, 'Other.cdr')
    app.Documents = Collection(source, other); app.ActiveDocument = other
    root = Shape(source.ActivePage.ActiveLayer, [rectangle(1, 2, 3, 2)])
    bridge = CorelBridge(); bridge.app = app; bridge._bind_target_document(source)
    return bridge, app, source, root
