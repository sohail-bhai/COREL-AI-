from __future__ import annotations

import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.text_ranges import FORMAT_PROPERTIES, unicode_text, safe_boundary
import test_typography as fixtures


def formatting():
    value = {name: 0 for name in FORMAT_PROPERTIES}
    value.update(Font='Arial', Size=12., Style=0, BulletFont='Arial', BulletSymbol='',
                 Bold=False, Italic=False, AutoHyphenate=False, HyphenateCapitals=False,
                 HyphenateAllCapWords=False, Alignment=1, LineSpacing=100., WordSpacing=100.)
    return value


class Characters:
    def __init__(self, story, first=0, last=None):
        self.story, self.first, self.last = story, first, last

    @property
    def Count(self):
        return (len(self.story.chunks) if self.last is None else self.last) - self.first

    def Item(self, index, count=1):
        self.story.reads += 1
        self.story.on_read(self.story)
        first = self.first + index - 1
        if not 1 <= index <= self.Count or first + count > self.first + self.Count:
            raise RuntimeError('Invalid native index')
        return Range(self.story, first, first + count)


class Range:
    def __init__(self, story, first, last):
        self.__dict__.update(story=story, first=first, last=last)

    @property
    def WideText(self):
        return ''.join(self.story.chunks[self.first:self.last])

    @WideText.setter
    def WideText(self, value):
        self.story.writes.append(('WideText', value))
        chunks = self.story.split(value)
        inherited = copy.deepcopy(self.story.styles[self.first])
        self.story.chunks[self.first:self.last] = chunks
        self.story.styles[self.first:self.last] = [copy.deepcopy(inherited) for _ in chunks]
        self.story.after_write(self.story)
        if self.story.fail_write:
            raise RuntimeError('Private C:/client/secret.cdr')

    @property
    def Start(self):
        return self.first

    @property
    def End(self):
        return self.last

    @property
    def Characters(self):
        return Characters(self.story, self.first, self.last)

    @property
    def CharBackFill(self):
        return SimpleNamespace(Type=0)

    def __getattr__(self, attr):
        if attr in FORMAT_PROPERTIES:
            values = [row[attr] for row in self.story.styles[self.first:self.last]]
            return values[0] if all(v == values[0] for v in values) else -2
        raise AttributeError(attr)

    def __setattr__(self, attr, value):
        if attr in FORMAT_PROPERTIES:
            self.story.writes.append((attr, value))
            for row in self.story.styles[self.first:self.last]:
                row[attr] = value
                if attr in ('Bold', 'Italic'):
                    row['Style'] = int(row['Bold']) + 2 * int(row['Italic'])
            self.story.after_write(self.story)
            if self.story.fail_write:
                raise RuntimeError('Private C:/client/secret.cdr')
        else:
            object.__setattr__(self, attr, value)


class Story:
    def __init__(self, content, utf16=False):
        self.utf16 = utf16
        self.chunks = self.split(content)
        self.styles = [formatting() for _ in self.chunks]
        self.Characters = Characters(self)
        self.writes, self.reads = [], 0
        self.on_read = lambda story: None
        self.after_write = lambda story: None
        self.fail_write = False
        self.selection = (0, 1)

    def split(self, value):
        if not self.utf16:
            return list(value)
        raw = value.encode('utf-16-le')
        return [raw[i:i + 2].decode('utf-16-le', 'surrogatepass') for i in range(0, len(raw), 2)]

    @property
    def WideText(self):
        return unicode_text(''.join(self.chunks))

    @property
    def Text(self):
        return self.WideText


class TextRangeTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.TypographyTests()
        fixture.setUp()
        self.bridge, self.shape, self.document = fixture.bridge, fixture.shape, fixture.document
        self.story = Story('AHelloZ')
        self.shape.Text.Story = self.story
        self.shape.PowerClip = None
        self.shape.Effects = fixtures.Collection()
        self.shape.GetMatrix = lambda: (1., 0., 0., 1., self.shape.PositionX, self.shape.PositionY)
        self.bridge._fill_readback = lambda native: {'type_code': 0, 'type': 'none', 'color': None}
        self.bridge._outline_readback = lambda native: {'type_code': 0, 'type': 'none', 'present': False,
            'width_raw': None, 'width_units': None, 'color': None}
        self.bridge._reference_for_shape = lambda document, shape: {'stable': True}
        self.bridge._selector_document = lambda *args: self.document
        self.bridge._resolve_object_reference = lambda *args, **kwargs: (self.shape, {'stable': True})

    def inspect(self, start=1, end=6):
        return self.bridge.inspect_text_range(start, end, object_name='Title')

    def edit(self, inspected=None, **changes):
        inspected = self.inspect() if inspected is None else inspected
        return self.bridge.edit_text_range(inspected['object_reference'], inspected['start'], inspected['end'],
            inspected['selected_text'], inspected['fingerprint'], **changes)

    def test_inspection_reports_exact_content_and_bounded_native_map(self):
        result = self.inspect()
        self.assertEqual((result['selected_text'], result['native_start_index'], result['native_count']), ('Hello', 2, 5))
        self.assertEqual(len(result['fingerprint']), 64)
        self.assertEqual(len(result['character_formats']), 5)
        self.assertFalse(self.story.writes)

    def test_native_selection_captured_once(self):
        self.shape.Text.Selection = Range(self.story, 1, 6)
        self.assertEqual(self.bridge.inspect_text_range(object_name='Title')['selected_text'], 'Hello')

    def test_one_based_inclusive_native_positions_are_mapped_without_assumption(self):
        with patch.object(Range, 'Start', property(lambda native: native.first + 1)), \
             patch.object(Range, 'End', property(lambda native: native.last)):
            self.shape.Text.Selection = Range(self.story, 1, 6)
            self.assertEqual(self.bridge.inspect_text_range(object_name='Title')['selected_text'], 'Hello')
            self.edit(self.inspect(), italic=True)

    def test_repeated_native_positions_are_refused(self):
        with patch.object(Range, 'Start', property(lambda native: 0)):
            with self.assertRaises(CorelBridgeError): self.inspect()

    def test_codepoint_and_utf16_emoji_mapping(self):
        for utf16 in (False, True):
            self.story = Story('A😀Z', utf16)
            self.shape.Text.Story = self.story
            result = self.inspect(1, 2)
            self.assertEqual(result['selected_text'], '😀')
            self.assertEqual(result['native_count'], 2 if utf16 else 1)
            self.edit(result, bold=True)
            self.assertFalse(self.story.styles[0]['Bold'])
            self.assertFalse(self.story.styles[-1]['Bold'])

    def test_mixed_formatting_preserved_inside_and_outside(self):
        self.story.styles[0]['Size'] = 31.
        self.story.styles[2]['Font'] = 'Times New Roman'
        self.story.styles[3]['Size'] = 24.
        self.story.styles[-1]['Italic'] = True
        before = copy.deepcopy(self.story.styles)
        result = self.edit(bold=True)
        for index in range(1, 6):
            before[index].update(Bold=True, Style=1)
        self.assertEqual(self.story.styles, before)
        self.assertTrue(result['surrounding_formatting_preserved'])

    def test_selected_replacement_preserves_suffix_format(self):
        self.story.styles[-1]['Size'] = 31.
        self.edit(replacement='Hi')
        self.assertEqual(self.story.WideText, 'AHiZ')
        self.assertEqual(self.story.styles[-1]['Size'], 31.)

    def test_replacement_with_utf16_surrogate_units(self):
        self.story = Story('A😀Z', True)
        self.shape.Text.Story = self.story
        self.edit(self.inspect(1, 2), replacement='two')
        self.assertEqual(self.story.WideText, 'AtwoZ')

    def test_mixed_replacement_refused_before_write(self):
        self.story.styles[2]['Italic'] = True
        with self.assertRaises(CorelBridgeError):
            self.edit(replacement='Hi')
        self.assertFalse(self.story.writes)

    def test_stale_content_style_and_location_refused(self):
        for change in ('content', 'style', 'location'):
            self.setUp()
            inspected = self.inspect()
            if change == 'content': self.story.chunks[2] = 'Q'
            if change == 'style': self.story.styles[-1]['Size'] = 99.
            if change == 'location': self.shape.PositionX = 77.
            with self.assertRaises(CorelBridgeError) as caught:
                self.edit(inspected, bold=True)
            self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)
            self.assertFalse(self.story.writes)

    def test_expected_text_mismatch_refused(self):
        inspected = self.inspect()
        inspected['selected_text'] = 'Wrong'
        with self.assertRaises(CorelBridgeError): self.edit(inspected, bold=True)
        self.assertFalse(self.story.writes)

    def test_concurrent_preflight_edit_preserved(self):
        inspected = self.inspect()
        def concurrent(story):
            story.styles[-1]['Size'] = 99.
        self.story.on_read = concurrent
        with self.assertRaises(CorelBridgeError): self.edit(inspected, bold=True)
        self.assertEqual(self.story.styles[-1]['Size'], 99.)
        self.assertFalse(self.story.writes)

    def test_collateral_formatting_detected_without_undo(self):
        self.story.after_write = lambda story: story.styles[-1].update(Size=77.)
        with self.assertRaises(CorelBridgeError) as caught: self.edit(bold=True, italic=True)
        self.assertEqual(caught.exception.code, ErrorCode.COREL_COM_ERROR)
        self.assertEqual(len(self.story.writes), 1)
        self.assertEqual(self.story.styles[-1]['Size'], 77.)

    def test_partial_native_failure_redacted_and_not_replayed(self):
        self.story.fail_write = True
        with self.assertRaises(CorelBridgeError) as caught: self.edit(bold=True)
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(len(self.story.writes), 1)

    def test_unsupported_layout_and_missing_format_refused(self):
        for failure in ('linked', 'clipped', 'missing'):
            self.setUp()
            if failure == 'linked': self.shape.Text.Frames = fixtures.Collection(object(), object())
            if failure == 'clipped': self.shape.PowerClip = object()
            if failure == 'missing': del self.story.styles[1]['LanguageID']
            with self.assertRaises(CorelBridgeError): self.edit(bold=True)
            self.assertFalse(self.story.writes)

    def test_protected_combining_joiner_and_crlf_boundaries(self):
        for content, start, end in [('Ae\u0301Z', 1, 2), ('A👩\u200d👩Z', 1, 2), ('A\r\nZ', 1, 2)]:
            self.story = Story(content)
            self.shape.Text.Story = self.story
            with self.assertRaises(CorelBridgeError): self.inspect(start, end)

    def test_invalid_input_and_empty_ranges(self):
        for start, end in [(True, 2), (-1, 2), (1, 1), (1, 99), (None, 2)]:
            with self.assertRaises(CorelBridgeError): self.inspect(start, end)
        for replacement in ('', '\n', '\t', '\x00', '\ud800'):
            with self.assertRaises(CorelBridgeError): self.edit(replacement=replacement)
        self.assertFalse(self.story.writes)

    def test_native_budget_and_malformed_unicode(self):
        self.story = Story('a' * 1025)
        self.shape.Text.Story = self.story
        with self.assertRaises(CorelBridgeError): self.inspect(0, 1)
        with self.assertRaises(CorelBridgeError): unicode_text('\ud800')

    def test_inconsistent_native_enumeration_refused(self):
        self.story.on_read = lambda story: setattr(story, 'chunks', ['A'] * 7)
        with self.assertRaises(CorelBridgeError): self.inspect()

    def test_no_selection_page_activation_unit_change_or_save(self):
        before = self.document.__dict__.copy()
        self.edit(bold=True)
        self.assertEqual(self.document.__dict__, before)

    def test_actual_result_and_request_schemas(self):
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator, ValidationError
        from corel_operator.results import success_result
        registry = json.loads((Path(__file__).resolve().parents[1] / 'catalog/mcp_tool_registry.json').read_text())
        tools = {t['name']: t for t in registry['tools']}
        sample_reference = registry['tool_examples']['edit_text_range']['request']['object_reference']
        self.bridge._reference_for_shape = lambda *args: sample_reference
        self.bridge._resolve_object_reference = lambda *args, **kwargs: (self.shape, sample_reference)
        inspected = self.inspect()
        edited = self.edit(inspected, bold=True)
        for name, result in [('inspect_text_range', inspected), ('edit_text_range', edited)]:
            schema = dict(schema_definitions=registry['schema_definitions'], allOf=[tools[name]['output_schema']])
            Draft202012Validator(schema).validate(success_result(name, result, 0))
            broken = copy.deepcopy(result)
            broken['unexpected'] = True
            with self.assertRaises(ValidationError): Draft202012Validator(schema).validate(success_result(name, broken, 0))
        inputs = dict(schema_definitions=registry['schema_definitions'], allOf=[tools['edit_text_range']['input_schema']])
        request = registry['tool_examples']['edit_text_range']['request']
        Draft202012Validator(inputs).validate(request)
        with self.assertRaises(ValidationError): Draft202012Validator(inputs).validate(dict(request, start=True))
