"""Synthetic page/layer ownership and failures for structure controls."""
from types import SimpleNamespace

from corel_operator.corel_bridge import CorelBridge
from fake_documents import attach_open_document
from test_object_references import Collection, Shape


class Layer:
    def __init__(self, page, name, master=False, special=False):
        self.ready = False
        self.Page = page; self.Name = name; self.Master = master; self.IsSpecialLayer = special
        self.Visible = True; self.Editable = True; self.Printable = True; self.Shapes = Collection()
        self.ready = True

    def __setattr__(self, key, value):
        if getattr(self, 'ready', False) and key in ('Name', 'Visible', 'Editable', 'Printable'):
            flags = self.Page.document.flags; self.Page.document.calls.append(('layer_set', key, value))
            if flags.get('ignore_' + key):
                return
            object.__setattr__(self, key, value)
            if flags.get('fail_' + key):
                raise RuntimeError('Private C:/secret/client.cdr')
            return
        object.__setattr__(self, key, value)

    def Activate(self):
        doc = self.Page.document; doc.calls.append(('layer_activate', self.Name))
        if not doc.flags.get('ignore_layer_restore'):
            self.Page.ActiveLayer = self; doc.ActivePage = self.Page

    def Delete(self):
        doc = self.Page.document; doc.calls.append(('layer_delete', self.Name))
        if doc.flags.get('fail_delete'):
            raise RuntimeError('Private deletion error')
        self.Page.Layers.items.remove(self)
        if self.Page.ActiveLayer is self:
            self.Page.ActiveLayer = self.Page.Layers.items[0]


class Page:
    def __init__(self, document, name, master=False):
        self.ready = False
        self.document = document; self.Name = name; self.SizeWidth = 8.; self.SizeHeight = 10.
        self.Layers = Collection(Layer(self, 'Master' if master else 'Artwork', master=master))
        self.ActiveLayer = self.Layers.items[0]; self.ready = True

    def __setattr__(self, key, value):
        if getattr(self, 'ready', False) and key == 'Name':
            self.document.calls.append(('page_set', key, value))
            if self.document.flags.get('ignore_page_name'):
                return
            object.__setattr__(self, key, value)
            if self.document.flags.get('fail_page_name'):
                raise RuntimeError('Private C:/secret/client.cdr')
            return
        object.__setattr__(self, key, value)

    @property
    def Index(self):
        return 0 if self is self.document.MasterPage else self.document.Pages.items.index(self) + 1

    @property
    def AllLayers(self):
        return Collection(*self.Layers.items, *self.document.MasterPage.Layers.items)

    @property
    def Shapes(self):
        return Collection(*(shape for layer in self.Layers.items for shape in layer.Shapes.items))

    def Activate(self):
        doc = self.document; doc.calls.append(('page_activate', self.Name))
        if not doc.flags.get('ignore_activate') and not (doc.flags.get('ignore_page_restore') and self is doc.Pages.items[0]):
            doc.ActivePage = self
        if doc.flags.get('activate_changes_layer'):
            self.ActiveLayer = doc.MasterPage.Layers.items[0]
        if doc.flags.get('activate_changes_membership'):
            self.Layers.items[0].Shapes.items.reverse()
        if doc.flags.get('fail_activate'):
            raise RuntimeError('Private activation error')

    def SetSize(self, width, height):
        doc = self.document; doc.calls.append(('size', width, height, doc.Unit))
        if not doc.flags.get('ignore_size'):
            self.SizeWidth, self.SizeHeight = width, height
        if doc.flags.get('change_original'):
            object.__setattr__(doc.Pages.items[0], 'Name', 'Changed by native call')

    def CreateLayer(self, name):
        doc = self.document; doc.calls.append(('create_layer', name))
        if doc.flags.get('existing_layer_receipt'):
            return self.Layers.items[0]
        layer = Layer(self, name)
        self.Layers.items.append(layer); self.ActiveLayer = layer; doc.ActivePage = self
        if doc.flags.get('populated_layer'):
            add_shape(layer, 'Unexpected', 909)
        if doc.flags.get('extra_layer'):
            self.Layers.items.append(Layer(self, 'Unknown'))
        if doc.flags.get('wrong_layer_name'):
            object.__setattr__(layer, 'Name', 'Wrong')
        if doc.flags.get('fail_create_layer'):
            raise RuntimeError('Private layer receipt lost')
        return Layer(doc.MasterPage, 'Foreign') if doc.flags.get('foreign_layer_receipt') else layer

    def Delete(self):
        doc = self.document; doc.calls.append(('page_delete', self.Name))
        if doc.flags.get('fail_delete'):
            raise RuntimeError('Private deletion error')
        doc.Pages.items.remove(self)
        if doc.ActivePage is self:
            doc.ActivePage = doc.Pages.items[0]


class Document:
    def __setattr__(self, key, value):
        if key == 'Unit' and hasattr(self, 'flags'):
            if value == 1 and self.flags.get('ignore_inch_units') or value == 3 and self.flags.get('ignore_unit_restore'):
                return
        object.__setattr__(self, key, value)

    def __init__(self):
        self.flags = {}; self.calls = []; self.Unit = 3; self.ReferencePoint = 9; self.Name = 'Target.cdr'
        self.MasterPage = Page(self, 'Master page', master=True)
        self.Pages = Collection(Page(self, 'Front'), Page(self, 'Back'))
        self.ActivePage = self.Pages.items[0]

    def AddPages(self, count):
        self.calls.append(('add_pages', count))
        if self.flags.get('existing_page_receipt'):
            return self.Pages.items[0]
        page = Page(self, 'New page'); self.Pages.items.append(page); self.ActivePage = page
        if self.flags.get('populated_page'):
            add_shape(page.ActiveLayer, 'Unexpected', 919)
        if self.flags.get('extra_page'):
            self.Pages.items.append(Page(self, 'Unknown'))
        if self.flags.get('fail_add_pages'):
            raise RuntimeError('Private page receipt lost')
        return Page(self, 'Foreign') if self.flags.get('foreign_page_receipt') else page

    def BeginCommandGroup(self, name):
        self.calls.append(('begin', name))
        if self.flags.get('fail_begin'):
            raise RuntimeError('Private begin group error')

    def EndCommandGroup(self):
        self.calls.append(('end',))
        if self.flags.get('fail_end'):
            raise RuntimeError('Private end group error')


def add_shape(layer, name, static_id):
    shape = Shape(name, static_id); shape.Layer = layer; shape.Page = layer.Page
    layer.Shapes.items.append(shape)
    return shape


def fixture():
    document = Document()
    add_shape(document.Pages.items[0].ActiveLayer, 'Front title', 101)
    add_shape(document.Pages.items[0].ActiveLayer, 'Front art', 102)
    add_shape(document.Pages.items[1].ActiveLayer, 'Back title', 201)
    bridge = CorelBridge(); app = SimpleNamespace(ActiveDocument=document)
    attach_open_document(bridge, document, app)
    return bridge, document
