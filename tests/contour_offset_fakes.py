"""Synthetic contour lifecycle, native receipts and independently owned trees."""
import copy
from types import SimpleNamespace

from test_layout import Collection
from test_process_colors import native_color, rgb
from vector_fakes import Shape as VectorShape, Curve, rectangle, fixture as vector_fixture


class Fill:
    def __init__(self, shape):
        self.shape = shape; self.Type = 0; self.UniformColor = None
    def ApplyUniformFill(self, color):
        self.Type = 1; self.UniformColor = color
        flags = self.shape.app.flags
        if flags.get('ignore_fill'):
            self.Type = 0
        if flags.get('corrupt_style_geometry'):
            self.shape.curve.paths[0].nodes[0].PositionX += 0.1
        if flags.get('style_failure'):
            raise RuntimeError('Private C:/secret/source.cdr')


class Outline:
    def __init__(self, shape):
        self.shape = shape; self.Type = 1; self.Width = 0.01; self.Color = native_color(rgb())
    def SetNoOutline(self):
        if not self.shape.app.flags.get('ignore_outline'):
            self.Type = 0; self.Width = 0.


class Transparency:
    def __init__(self, shape):
        self.shape = shape; self.Type = 0; self.Uniform = 0; self.AppliedTo = 0; self.MergeMode = 0
    def ApplyNoTransparency(self):
        if not self.shape.app.flags.get('ignore_transparency'):
            self.Type = 0


class Shape(VectorShape):
    def __init__(self, layer, curve, name='ContourSource', code=3):
        super().__init__(layer, curve, name, code)
        self.Effects = Collection(); self.PowerClip = None
        self.Fill = Fill(self); self.Outline = Outline(self); self.Transparency = Transparency(self)
    def bounds(self):
        base = super().bounds()
        if getattr(self.app, 'flags', {}).get('controller_effect_bounds') and hasattr(self, 'Effects') and self.Effects.Count:
            children = self.Effects.items[0].Contour.ContourGroup.Shapes.items
            boxes = [base] + [s.bounds() for s in children]
            x = min(b[0] for b in boxes); y = min(b[1] for b in boxes)
            return x, y, max(b[0] + b[2] for b in boxes) - x, max(b[1] + b[3] for b in boxes) - y
        return base
    def Duplicate(self, x, y):
        flags = self.app.flags
        if flags.get('reuse_duplicate'):
            return self
        curve = self.curve if flags.get('shared_source_curve') else self.curve.clone()
        if flags.get('shared_foreign_curve'):
            curve = self.app.other_source.curve
        result = Shape(self.Layer, curve, self.Name + ' (2)', self.Type)
        for name, attributes in (('Fill', ('Type', 'UniformColor')), ('Outline', ('Type', 'Width', 'Color')),
                                 ('Transparency', ('Type', 'Uniform', 'AppliedTo', 'MergeMode'))):
            for attribute in attributes:
                setattr(getattr(result, name), attribute, copy.deepcopy(getattr(getattr(self, name), attribute)))
        if self.Fill.Type == 2:
            fountain = copy.copy(self.Fill.Fountain)
            fountain.Colors = copy.copy(fountain.Colors)
            fountain.Colors.items = copy.deepcopy(self.Fill.Fountain.Colors.items)
            fountain.Colors.fountain = fountain; fountain.fill = result.Fill
            result.Fill.Fountain = fountain
        self.app.duplicates.append(result)
        if flags.get('duplicate_geometry'):
            result.curve.paths[0].nodes[0].PositionX += 0.1
        if flags.get('duplicate_node_type'):
            result.curve.paths[0].nodes[0].Type = 1
        return result
    def ConvertToCurves(self):
        if not self.app.flags.get('ignore_conversion'):
            self.Type = 3
    def CreateContour(self, direction, offset, steps, blend, outline, fill, fill2, spacing, color_accel, cap, corner, miter):
        self.app.calls.append(('contour', direction, offset, steps, cap, corner, miter))
        if self.app.flags.get('create_failure'):
            raise RuntimeError('Private C:/secret/source.cdr')
        x, y, width, height = self.bounds()
        generated = []
        for step in range(1, steps + 1):
            distance = offset * step * (1 if direction == 1 else -1)
            if width + 2 * distance <= 0 or height + 2 * distance <= 0:
                continue
            path = rectangle(x - distance, y - distance, width + 2 * distance, height + 2 * distance)
            if self.app.flags.get('wrong_extent'):
                path = rectangle(x, y, width, height)
            curve = Curve.from_paths(self.app, [path])
            if self.app.flags.get('shared_generated_curve'):
                curve = self.app.other_source.curve
            shape = Shape(self.Layer, curve, 'NativeContour')
            shape.Fill.Type = 1; shape.Fill.UniformColor = fill
            shape.Transparency.Type = 1; shape.Transparency.Uniform = 35
            generated.append(shape)
        if self.app.flags.get('compound_output') and generated:
            combined = Shape(self.Layer, Curve.from_paths(self.app, [s.curve.paths[0].data() for s in generated]), 'NativeCompound')
            combined.Transparency.Type = 1; combined.Transparency.Uniform = 35
            for shape in generated:
                shape.Delete()
            generated = [combined]
        if self.app.flags.get('foreign_child'):
            generated.append(self.app.other_source)
        if self.app.flags.get('nested_group'):
            generated = [Group(self.Layer, generated, 7)]
        group = Group(self.Layer, generated, 13)
        effect = Effect(self, group, direction, offset, steps, blend, outline, fill, fill2, spacing, color_accel, cap, corner, miter)
        self.Effects.items = [effect]; group.effect = effect
        for name, value in self.app.flags.get('parameter_changes', {}).items():
            setattr(effect.Contour, name, value)
        if self.app.flags.get('wrong_effect_type'):
            effect.Type = 5
        if self.app.flags.get('wrong_parent'):
            effect.Contour.Parent = SimpleNamespace()
        if self.app.flags.get('unknown_created_root'):
            Shape(self.Layer, Curve.from_paths(self.app, [rectangle(20, 20)]), 'UnknownNativeRoot')
        if self.app.flags.get('source_corruption'):
            self.app.original.curve.paths[0].nodes[0].PositionX += 0.1
        if self.app.flags.get('controller_corruption'):
            self.curve.paths[0].nodes[0].PositionX += 0.1
        if self.app.flags.get('create_late_failure'):
            if self.app.flags.get('stray_controller'):
                self.Layer.Shapes.items.remove(self); self.Page.Shapes.items.remove(self)
                self.Layer = SimpleNamespace(Page=self.Page)
                self.app.stray = self
            raise RuntimeError('Private C:/secret/source.cdr')
        return effect
    def Delete(self):
        if self.app.flags.get('fail_delete'):
            raise RuntimeError('Private C:/secret/source.cdr')
        self.app.deleted.append(self.StaticID)
        for effect in list(self.Effects.items):
            group = effect.Contour.ContourGroup
            if group in self.Layer.Shapes.items:
                group.Delete()
        super().Delete()


class Group(Shape):
    def __init__(self, layer, children, code):
        super().__init__(layer, Curve.from_paths(layer.Page.document.app, [rectangle()]), 'NativeContourGroup', code)
        self.Shapes = Collection(*children); self.effect = None
        for child in children:
            if child in layer.Shapes.items:
                layer.Shapes.items.remove(child); self.Page.Shapes.items.remove(child)
            child.ParentGroup = self
    def Ungroup(self):
        if self.app.flags.get('ungroup_failure'):
            raise RuntimeError('Private C:/secret/source.cdr')
        children = list(self.Shapes.items); self.Shapes.items = []
        for child in children:
            child.ParentGroup = None
            self.Layer.Shapes.items.append(child); self.Page.Shapes.items.append(child)
        self.Delete()
    def Delete(self):
        if self.app.flags.get('fail_delete'):
            raise RuntimeError('Private C:/secret/source.cdr')
        for child in list(self.Shapes.items):
            self.Layer.Shapes.items.append(child); self.Page.Shapes.items.append(child)
            child.ParentGroup = None; child.Delete()
        self.Shapes.items = []
        if self.effect is not None:
            self.effect.controller.Effects.items = []
        super().Delete()


class Effect:
    def __init__(self, controller, group, direction, offset, steps, blend, outline, fill, fill2, spacing, color_accel, cap, corner, miter):
        self.controller = controller; self.Type = 6
        self.Contour = SimpleNamespace(Parent=self, ContourGroup=group, Direction=direction, Offset=offset, Steps=steps,
                                      ColorBlendType=blend, OutlineColor=outline, FillColor=fill, FillColorTo=fill2,
                                      SpacingAcceleration=spacing, ColorAcceleration=color_accel, EndCapType=cap,
                                      CornerType=corner, MiterLimit=miter)
    def Separate(self):
        flags = self.controller.app.flags
        if flags.get('stray_leaf_failure'):
            group = self.Contour.ContourGroup
            child = group.Shapes.items.pop()
            child.ParentGroup = None; child.Layer = SimpleNamespace(Page=child.Page)
            self.controller.app.stray = child
            raise RuntimeError('Private C:/secret/source.cdr')
        if flags.get('separate_failure'):
            raise RuntimeError('Private C:/secret/source.cdr')
        self.controller.Effects.items = []
        group = self.Contour.ContourGroup; group.Type = 7
        if flags.get('replace_container'):
            children = list(group.Shapes.items); group.Shapes.items = []
            group.Delete()
            group = Group(self.controller.Layer, children, 7)
        if flags.get('separate_geometry') and group.Shapes.items:
            group.Shapes.items[0].curve.paths[0].nodes[0].PositionX += 0.1
        if flags.get('separate_foreign_receipt'):
            return Collection(self.controller.app.original)
        return Collection(self.controller, group)


def fixture():
    app, document, layer = vector_fixture()
    app.flags = {}; app.deleted = []
    app.CreateRGBColor = lambda r, g, b: native_color({'model': 'rgb', 'red': r, 'green': g, 'blue': b})
    app.CreateCMYKColor = lambda c, m, y, k: native_color({'model': 'cmyk', 'cyan': c, 'magenta': m, 'yellow': y, 'black': k})
    source = Shape(layer, Curve.from_paths(app, [rectangle(1, 1, 3, 2)]))
    app.original = source
    app.other_source = Shape(layer, Curve.from_paths(app, [rectangle(10, 10)]), 'OtherSource')
    return app, document, layer, source
