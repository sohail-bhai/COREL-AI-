"""Guarded whole-frame horizontal spacing through X7's explicit structure setter."""
from __future__ import annotations

import math

from .errors import CorelBridgeError, ErrorCode
from .native_tracking import tracked_mutation
from .typography import MAX_TEXT_CHARS, finite_number, layout_readback, read_property, style_readback

ALL_FRAMES = 2  # Installed cdrTextFrames.cdrAllFrames; no range-index assumptions.
FIELDS = {
    'character_spacing_percent': 'CharacterSpacing', 'word_spacing_percent': 'WordSpacing',
    'line_spacing': 'LineSpacing', 'spacing_type_code': 'LineSpacingType',
    'paragraph_before': 'BeforeParagraphSpacing', 'paragraph_after': 'AfterParagraphSpacing',
}
SCALARS = {
    'character_spacing_percent': 'CharSpacing', 'word_spacing_percent': 'WordSpacing',
    'line_spacing': 'LineSpacing', 'spacing_type_code': 'LineSpacingType',
    'paragraph_before': 'ParaSpacingBefore', 'paragraph_after': 'ParaSpacingAfter',
}
LIMITS = ('MaxCharacterSpacing', 'MinWordSpacing', 'MaxWordSpacing')
GEOMETRY = ('PositionX', 'PositionY', 'SizeWidth', 'SizeHeight')


def refuse(message, code=ErrorCode.UNSUPPORTED_IN_PROFILE):
    raise CorelBridgeError(message, code)


def spacing_values(structure):
    values = {key: read_property(structure, attr, 'integer' if key == 'spacing_type_code' else 'number')
              for key, attr in FIELDS.items()}
    if (any(value is None for value in values.values()) or values['spacing_type_code'] not in (0, 1, 2)
            or not -100 <= values['character_spacing_percent'] <= 2000
            or not 0 <= values['word_spacing_percent'] <= 2000
            or values['line_spacing'] <= 0 or values['paragraph_before'] < 0 or values['paragraph_after'] < 0):
        refuse('Existing spacing is mixed, unavailable or outside the supported profile.')
    return values


def agrees(expected, actual):
    return all(actual.get(key) is not None and (
        actual[key] == value if key == 'spacing_type_code'
        else math.isclose(value, actual[key], abs_tol=.01, rel_tol=0)) for key, value in expected.items())


class HorizontalSpacingMixin:
    def _horizontal_frame_state(self, text, shape, text_type):
        if text_type == 0:
            return None
        frame = text.Frame
        count = read_property(frame, 'ColumnCount', 'integer')
        vertical = read_property(frame, 'VerticalAlignment', 'integer')
        if (frame.IsInsideContainer is not False or frame.IsFittedToPath is not False
                or not self._same_com_object(frame.FrameShape, shape, strict=True)
                or count is None or not 1 <= count <= 20 or vertical is None):
            refuse('Paragraph spacing requires an ordinary owned frame with at most 20 readable columns.')
        width = self._layout_method(frame, 'ColumnWidth')
        gutter = self._layout_method(frame, 'ColumnGutter') if count > 1 else None
        columns = []
        for index in range(1, count + 1):
            raw_width = width(index)
            raw_gutter = gutter(index) if index < count else None
            if (type(raw_width) not in (int, float) or not math.isfinite(raw_width) or raw_width <= 0
                    or index < count and (type(raw_gutter) not in (int, float)
                        or not math.isfinite(raw_gutter) or raw_gutter < 0)):
                refuse('Native column geometry cannot be preserved.')
            columns.append((raw_width, raw_gutter))
        return {'vertical_alignment': vertical, 'columns': columns}

    @tracked_mutation
    def set_text_horizontal_spacing(self, character_spacing_percent=None, word_spacing_percent=None,
                                    object_name='', shape_index=0, object_reference=None):
        requested = {}
        for key, value, minimum in (('character_spacing_percent', character_spacing_percent, -100),
                                    ('word_spacing_percent', word_spacing_percent, 0)):
            if value is not None:
                requested[key] = finite_number(value, key, minimum, 2000)
        if not requested:
            refuse('Supply character_spacing_percent or word_spacing_percent.', ErrorCode.INVALID_ARGUMENT)
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        if object_reference is not None:
            shape, _ = self._resolve_object_reference(document, object_reference, mutation=True)
        if identity['shape_type_code'] != self.adapter.CDR_TEXT_SHAPE:
            refuse('The selected object is not a text shape.', ErrorCode.INVALID_ARGUMENT)
        try:
            text, story = shape.Text, shape.Text.Story
            layout = layout_readback(text, story)
            if layout['text_type_code'] not in (0, 1) or layout['frame_count'] != 1:
                refuse('Horizontal spacing requires one unfitted, unlinked frame.')
            frame_state = self._horizontal_frame_state(text, shape, layout['text_type_code'])
            content = story.Text
            if type(content) is not str or not content or len(content) > MAX_TEXT_CHARS:
                refuse('Text content is unavailable or exceeds the bounded preservation scope.')
            style = style_readback(story)
            if style['unavailable_or_mixed_properties']:
                refuse('Horizontal spacing requires readable uniform basic text formatting.')
            getter, setter = getattr(text, 'GetSpaceProperties', None), getattr(text, 'SetSpaceProperties', None)
            align_getter = getattr(text, 'GetAlignProperties', None)
            creator = getattr(self.app, 'CreateStructSpaceProperties', None)
            if not all(callable(method) for method in (getter, setter, align_getter, creator)):
                refuse('The installed whole-frame spacing structure interface is unavailable.')
            original = getter(ALL_FRAMES)
            before = spacing_values(original)
            alignment = align_getter(ALL_FRAMES)
            limits = {attr: read_property(alignment, attr, 'number') for attr in LIMITS}
            if (any(value is None for value in limits.values())
                    or not -100 <= limits['MaxCharacterSpacing'] <= 2000
                    or not 0 <= limits['MinWordSpacing'] <= limits['MaxWordSpacing'] <= 2000):
                refuse('Native justification spacing limits are mixed or unavailable.')
            if ('character_spacing_percent' in requested
                    and requested['character_spacing_percent'] > limits['MaxCharacterSpacing']
                    or 'word_spacing_percent' in requested and not
                    limits['MinWordSpacing'] <= requested['word_spacing_percent'] <= limits['MaxWordSpacing']):
                refuse('Requested spacing exceeds the existing native justification limits.', ErrorCode.INVALID_ARGUMENT)
            scalar_values = lambda: {key: read_property(story, attr,
                'integer' if key == 'spacing_type_code' else 'number') for key, attr in SCALARS.items()}
            if not agrees(before, scalar_values()):
                refuse('Native scalar and percentage-structure spacing readbacks disagree.')
            target_reference = self._reference_for_shape(document, shape)
            raw_bounds = lambda: {attr: read_property(shape, attr, 'number') for attr in GEOMETRY}
            bounds = raw_bounds()
            context = (read_property(document, 'Unit', 'integer'), read_property(document, 'ReferencePoint', 'integer'))
            if (any(value is None for value in bounds.values()) or bounds['SizeWidth'] <= 0
                    or bounds['SizeHeight'] <= 0 or target_reference is None or None in context):
                refuse('Native geometry or complete target identity cannot be inspected.')
            # Build a separate structure; never edit a possibly bound getter result.
            pending = creator()
            if pending is None or self._same_com_object(pending, original, strict=True):
                refuse('A separate spacing structure could not be created.')
            expected = dict(before, **requested)
            for key, attr in FIELDS.items():
                setattr(pending, attr, expected[key])
            if not agrees(expected, spacing_values(pending)):
                refuse('The detached structure cannot represent the requested spacing.')
            self._resolve_object_reference(document, target_reference, mutation=True)
            if (spacing_values(getter(ALL_FRAMES)) != before or not agrees(before, scalar_values())
                    or story.Text != content or style_readback(story) != style
                    or {attr: read_property(align_getter(ALL_FRAMES), attr, 'number') for attr in LIMITS} != limits
                    or layout_readback(text, story)['text_type_code'] != layout['text_type_code']
                    or layout_readback(text, story)['frame_count'] != 1
                    or self._horizontal_frame_state(text, shape, layout['text_type_code']) != frame_state
                    or raw_bounds() != bounds or (document.Unit, document.ReferencePoint) != context):
                refuse('Text changed during horizontal-spacing preflight; inspect it again.', ErrorCode.INVALID_ARGUMENT)
            self._note_mutation()
            setter(ALL_FRAMES, pending)
            actual = spacing_values(getter(ALL_FRAMES))
            after_layout = layout_readback(text, story)
            if (not agrees(expected, actual) or not agrees(expected, scalar_values())
                    or story.Text != content or style_readback(story) != style
                    or {attr: read_property(align_getter(ALL_FRAMES), attr, 'number') for attr in LIMITS} != limits
                    or after_layout['text_type_code'] != layout['text_type_code'] or after_layout['frame_count'] != 1
                    or self._horizontal_frame_state(text, shape, layout['text_type_code']) != frame_state
                    or (document.Unit, document.ReferencePoint) != context):
                refuse('Native horizontal spacing changed preserved state or differs from the request.', ErrorCode.COREL_COM_ERROR)
            if layout['text_type_code'] == 1 and raw_bounds() != bounds:
                refuse('Native horizontal spacing changed the paragraph frame bounds.', ErrorCode.COREL_COM_ERROR)
            actual_bounds = self._typography_bounds(document, shape)
            self._resolve_object_reference(document, target_reference, mutation=True)
            if (not agrees(actual, spacing_values(getter(ALL_FRAMES))) or not agrees(actual, scalar_values())
                    or story.Text != content or style_readback(story) != style
                    or (document.Unit, document.ReferencePoint) != context
                    or layout_readback(text, story) != after_layout
                    or self._horizontal_frame_state(text, shape, layout['text_type_code']) != frame_state
                    or {attr: read_property(align_getter(ALL_FRAMES), attr, 'number') for attr in LIMITS} != limits
                    or layout['text_type_code'] == 1 and raw_bounds() != bounds):
                refuse('Text changed during final horizontal-spacing readback.', ErrorCode.COREL_COM_ERROR)
            identity['object_reference'] = self._reference_for_shape(document, shape)
            return {'updated': True, 'object': identity, 'formatting_scope': 'whole_story',
                    'spacing_unit': 'percent_space_character', 'requested_spacing': requested,
                    'before_spacing': before, 'actual_spacing': actual, 'content_preserved': True,
                    'actual_bounds_inches': actual_bounds, 'layout': after_layout}
        except CorelBridgeError:
            if self._operation_mutation_started:
                refuse('CorelDRAW horizontal-spacing result requires inspection and reconciliation.', ErrorCode.COREL_COM_ERROR)
            raise
        except Exception as exc:
            raise CorelBridgeError('CorelDRAW could not apply or inspect horizontal spacing.', ErrorCode.COREL_COM_ERROR) from exc
