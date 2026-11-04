"""Synthetic native bitmap pixel grid, crop envelope and affine placement."""
from types import SimpleNamespace

from corel_operator.corel_bridge import CorelBridge
from fake_documents import attach_open_document
from test_layout import Collection, Shape as LayoutShape
from vector_fakes import Curve, fixture as vector_fixture


class Bitmap:
    def __init__(self, shape):
        self.shape = shape; self.SizeWidth = 1200; self.SizeHeight = 600
        self.ResolutionX = 72; self.ResolutionY = 72; self.Mode = 5
        self.ExternallyLinked = False; self.Embedded = True; self.Cropped = True
        self.CropEnvelopeModified = False; self.override_box = None; self.fail_box = False

    @property
    def BoundingBoxPath(self):
        if self.fail_box:
            raise RuntimeError('Private C:/secret/source.png')
        if self.override_box is not None:
            return self.override_box
        a, b, c, d, x, y = self.shape.matrix
        points = [{'x': a * u + c * v + x, 'y': b * u + d * v + y}
            for u, v in ((0, 0), (self.shape.width, 0), (self.shape.width, self.shape.height), (0, self.shape.height))]
        return Curve.from_paths(self.shape.app, [{'start': points[0], 'closed': True,
            'segments': [{'type': 'line', 'end': point} for point in points[1:] + points[:1]]}])


class Shape(LayoutShape):
    def __init__(self, layer, name='Bitmap', code=5):
        super().__init__(name, 301, 0, 0, 4., 2.)
        self.app = layer.Page.document.app; self.Layer = layer; self.Page = layer.Page; self.Type = code
        self.Bitmap = Bitmap(self); self.Effects = Collection(); self.PowerClip = None; self.Shapes = Collection()
        self.crop_bounds = None
        layer.Shapes.items.append(self); self.Page.Shapes.items.append(self)

    def bounds(self):
        return super().bounds() if self.crop_bounds is None else self.crop_bounds


def fixture():
    app, document, layer = vector_fixture()
    shape = Shape(layer); bridge = CorelBridge(); attach_open_document(bridge, document, app)
    reference = bridge._reference_for_shape(document, shape)
    return bridge, document, shape, reference


def nest(shape):
    parent = LayoutShape('Bitmap Group', 401, 0, 0, 4., 2.)
    parent.Type = 7; parent.Shapes = Collection(shape); parent.Layer = shape.Layer; parent.Page = shape.Page
    parent.Effects = Collection(); parent.PowerClip = None
    shape.Layer.Shapes.items.remove(shape); shape.Page.Shapes.items.remove(shape)
    shape.Layer.Shapes.items.append(parent); shape.Page.Shapes.items.append(parent); shape.ParentGroup = parent
    return parent
