"""Editable paragraph/frame scene model with native Single sizes and measured overflow."""
import copy
import struct
from types import SimpleNamespace

from powerclip_fakes import Shape
from test_layout import Collection
from test_typography import Story as BasicStory


class Story(BasicStory):
    def __init__(self, app):
        super().__init__('Editable paragraph नमस्ते 😀\rSecond line')
        self.__dict__.update(Size=18., ParaSpacingBefore=0., ParaSpacingAfter=0., app=app)

    def __setattr__(self, key, value):
        if key == 'Size' and 'app' in self.__dict__:
            value = struct.unpack('<f', struct.pack('<f', value))[0]
            self.__dict__[key] = value
            self.writes.append((key, value))
            self.app.size_probes.append((self, value))
            self.app.on_size(self)
            if self.app.fail_size:
                raise RuntimeError('Private C:/client/secret.cdr')
        else:
            super().__setattr__(key, value)

    def __deepcopy__(self, memo):
        result = Story(self.app)
        result.__dict__.update({k: copy.deepcopy(v, memo) for k, v in self.__dict__.items() if k != 'app'})
        return result


class Text:
    def __init__(self, app, owner=None, story=None):
        self.app, self.owner, self.Story = app, owner, story or Story(app)
        self.Type = 1
        self.container = False
        self.fitted = False

    @property
    def Overflow(self):
        if self.app.unknown_overflow:
            return None
        return self.Story.Size > self.app.fitting_threshold

    @property
    def Frame(self):
        return SimpleNamespace(IsInsideContainer=self.container, IsFittedToPath=self.fitted,
            FrameShape=self.owner, VerticalAlignment=0, ColumnCount=self.app.column_count,
            ColumnWidth=lambda index: self.app.column_width,
            ColumnGutter=lambda index: self.app.column_gutter if index < self.app.column_count else None,
            Fill=SimpleNamespace(Type=0), Outline=SimpleNamespace(Type=0, Width=0.))

    @property
    def Frames(self):
        return Collection(*[self.Frame for _ in range(self.app.frame_count)])

    def __deepcopy__(self, memo):
        result = Text(self.app, story=copy.deepcopy(self.Story, memo))
        result.Type, result.container, result.fitted = self.Type, self.container, self.fitted
        return result


class Paragraph(Shape):
    def __init__(self, layer, paths, name='Body'):
        super().__init__(layer, paths, name, 6)
        self.Text = Text(self.app, self)
        self.Effects = Collection()

    def Duplicate(self, x, y):
        output = super().Duplicate(x, y)
        if output is not self:
            output.Text.owner = output
            output.Effects = Collection()
        self.app.on_duplicate(output)
        return output


def prepare(app):
    app.size_probes = []
    app.fail_size = False
    app.on_size = lambda story: None
    app.on_duplicate = lambda output: None
    app.fitting_threshold = 12.
    app.unknown_overflow = False
    app.frame_count = 1
    app.column_count = 1
    app.column_width = 3.
    app.column_gutter = .25
