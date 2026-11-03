"""Synthetic endpoint-inclusive native gradient objects; no Corel connection."""
from types import SimpleNamespace

from test_layout import Collection
from test_process_colors import Fill as ProcessFill


class Stops(Collection):
    def __init__(self, fountain, start, end):
        super().__init__(self.stop(0, start), self.stop(100, end))
        self.fountain = fountain
        self.ignore_add = False
        self.convert_add = False
        self.calls = []

    @staticmethod
    def stop(position, color):
        return SimpleNamespace(Position=position, Color=color, MidPoint=50, BlendType=0, Opacity=255)

    def Add(self, color, position):
        self.calls.append(position)
        if not self.ignore_add:
            item = self.stop(position, color)
            if self.convert_add:
                item.Color = self.items[0].Color
            self.items.append(item)
            self.items.sort(key=lambda s: s.Position)
            self.fountain.BlendType = 3


class Fountain:
    def __init__(self, fill, start, end, kind, angle, steps, pad, midpoint, blend, cx, cy):
        self.fill = fill
        self.Type, self.Angle, self.Steps = kind, angle, steps
        self.EdgePad, self.MidPoint, self.BlendType = pad, midpoint, blend
        self.CenterOffsetX, self.CenterOffsetY = cx, cy
        self.SmoothBlend, self.SpreadMethod, self.Anisotropic = False, 2, True
        self.IsTransparent, self.MergeMode, self.BlendAcceleration = True, 4, 0.5
        self.HasHSBBlends, self.HasNonLinearBlends = False, False
        self.ScaleX, self.ScaleY, self.Skew = 1., 1., 0.
        self.StartX, self.StartY, self.EndX, self.EndY, self.End2X, self.End2Y = 0., 0., 1., 0., 0., 1.
        self.Colors = Stops(self, start, end)
        self.opaque_calls = 0

    @property
    def StartColor(self):
        return self.Colors.items[0].Color

    @property
    def EndColor(self):
        return self.Colors.items[-1].Color

    def MakeOpaque(self):
        self.opaque_calls += 1
        if not self.fill.ignore_opaque:
            self.IsTransparent = False
        for name, value in self.fill.final_changes.items():
            setattr(self, name, value)
        if self.fill.drop_stop:
            self.Colors.items.pop(1)
        if self.fill.corrupt_outline:
            self.fill.shape.Outline.Width += 0.1
        if self.fill.corrupt_transparency:
            self.fill.shape.Transparency.Uniform += 1
        if self.fill.corrupt_text:
            self.fill.shape.Text.Story.Text += 'Changed'


class Fill(ProcessFill):
    def __init__(self, shape):
        super().__init__(shape)
        self.calls = []
        self.ignore_opaque = self.drop_stop = False
        self.corrupt_outline = self.corrupt_transparency = self.corrupt_text = False
        self.final_changes = {}
        self.after_create = None

    def ApplyFountainFill(self, *args):
        self.calls.append(args)
        if self.ignore:
            return
        self.Type = 2
        self.Fountain = Fountain(self, *args)
        if self.mutate:
            self.shape.curve.paths[0].nodes[0].PositionX += 0.1
        if self.after_create:
            self.after_create(self.Fountain)
        if self.fail:
            raise RuntimeError('Private C:/secret/source.cdr')
        return self.Fountain
