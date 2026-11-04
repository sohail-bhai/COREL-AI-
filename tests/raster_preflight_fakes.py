"""Page/master/group/clip raster fixtures without native mutation."""
from types import SimpleNamespace
from organization_fakes import fixture as organization_fixture
from test_layout import Collection, Shape as LayoutShape
from bitmap_fakes import Bitmap


class Shape(LayoutShape):
    def __init__(self, layer, name='Bitmap', static_id=501, code=5):
        super().__init__(name, static_id, 0, 0, 4., 2.)
        self.Layer = layer; self.Page = layer.Page; self.Type = code
        self.app = layer.Page.document.app; self.Shapes = Collection(); self.Effects = Collection()
        self.PowerClip = None; self.PowerClipParent = None
        if code == 5:
            self.Bitmap = Bitmap(self); self.Bitmap.OPILinked = False; self.Bitmap.IsEPS = False; self.Bitmap.LinkFileName = ''
        layer.Shapes.items.append(self)


def fixture():
    bridge, document = organization_fixture(); document.app = bridge.app
    document.Dirty = False; document.SelectionRange = Collection(); document.FullFileName = ''
    for page in [document.MasterPage, *document.Pages.items]:
        for layer in page.Layers.items: layer.Shapes.items.clear()
    front = Shape(document.Pages.items[0].ActiveLayer)
    back = Shape(document.Pages.items[1].ActiveLayer, 'Back bitmap', 601)
    return bridge, document, front, back


def group(children, name='Group', static_id=801):
    layer = children[0].Layer
    parent = Shape(layer, name, static_id, 7); parent.Shapes = Collection(*children)
    for child in children:
        layer.Shapes.items.remove(child); child.ParentGroup = parent
    return parent


def clip(children, static_id=901):
    frame = Shape(children[0].Layer, 'Clip', static_id, 1)
    frame.PowerClip = SimpleNamespace(Parent=frame, Shapes=Collection(*children))
    for child in children:
        child.Layer.Shapes.items.remove(child); child.PowerClipParent = frame
    return frame
