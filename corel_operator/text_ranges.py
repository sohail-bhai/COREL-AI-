"""Bounded Unicode mapping and per-character preservation for selected text."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import struct
import unicodedata

from .errors import CorelBridgeError, ErrorCode
from .native_tracking import tracked_mutation
from .text_fitting import ordinary_appearance
from .typography import STYLE_ATTRIBUTES, UNDERLINES, validate_style, layout_readback

MAX_NATIVE_CHARACTERS = 1024
MAX_CODEPOINTS = 2048
# Installed X7 scalar formatting setters. Position/content setters are excluded.
FORMAT_PROPERTIES = (
    'Font', 'Size', 'Style', 'Bold', 'Italic', 'Underline', 'Strikethru', 'Overscore',
    'Position', 'Case', 'CharAngle', 'Alignment', 'FirstLineIndent', 'HorizShift',
    'VertShift', 'LeftIndent', 'RightIndent', 'MinWordSpacing', 'MaxWordSpacing',
    'MaxCharSpacing', 'ParaSpacingBefore', 'ParaSpacingAfter', 'CharSpacing',
    'LineSpacing', 'LineSpacingType', 'WordSpacing', 'AutoHyphenate', 'HyphenHotZone',
    'HyphenMinCharsBefore', 'HyphenMinCharsAfter', 'HyphenMinWordLength',
    'HyphenateCapitals', 'LanguageID', 'CharSet', 'RangeKerning',
    'DropCapLinesDropped', 'DropCapDistanceFromText', 'DropCapHangingIndent',
    'BulletFont', 'BulletSymbol', 'BulletSize', 'BulletBaselineShift',
    'BulletHorizontalPosition', 'BulletHangingIndent', 'HyphenateAllCapWords', 'TextFormatter',
)


def refuse(message, code=ErrorCode.UNSUPPORTED_IN_PROFILE):
    raise CorelBridgeError(message, code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     allow_nan=False).encode()).hexdigest()


def unicode_text(value):
    if type(value) is not str or '\x00' in value or len(value) > MAX_CODEPOINTS:
        refuse('Unicode text is unavailable or outside the bounded range profile.')
    try:
        # Join UTF-16 surrogate halves only after collecting native characters.
        return value.encode('utf-16-le', 'surrogatepass').decode('utf-16-le')
    except UnicodeError:
        refuse('Native Unicode text contains an unpaired surrogate.')


def safe_boundary(content, offset):
    if offset in (0, len(content)):
        return True
    left, right = content[offset - 1], content[offset]
    # Conservative boundary policy for common combining/joined sequences. This
    # is not a claim of full grapheme segmentation or shaped-glyph acceptance.
    return not (unicodedata.category(right).startswith('M') or left == '\u200d'
                or right == '\u200d' or left == '\r' and right == '\n'
                or 0x1F3FB <= ord(right) <= 0x1F3FF
                or 0x1F1E6 <= ord(left) <= 0x1F1FF and 0x1F1E6 <= ord(right) <= 0x1F1FF
                or 0x1100 <= ord(left) <= 0x11FF or 0x1100 <= ord(right) <= 0x11FF)


class TextRangesMixin:
    def _range_format(self, native):
        result = {}
        for attr in FORMAT_PROPERTIES:
            value = getattr(native, attr)
            if attr in ('Bold', 'Italic', 'AutoHyphenate', 'HyphenateCapitals', 'HyphenateAllCapWords'):
                if type(value) is int and value in (0, -1):
                    value = value == -1
                if type(value) is not bool:
                    refuse('Character boolean formatting is mixed or unavailable.')
            if (type(value) not in (str, int, float, bool) or type(value) is str and len(value) > 200
                    or type(value) in (int, float) and not math.isfinite(value)):
                refuse('Complete native character formatting cannot be inspected.')
            result[attr] = value
        if not result['Font'] or type(result['Font']) is not str or not 1 <= result['Size'] <= 500:
            refuse('Character font/size is unreadable or outside 1–500 points.')
        fill, outline = self._fill_readback(native), self._outline_readback(native)
        if not ordinary_appearance(fill, outline):
            refuse('Character fill/outline exceeds exact process-color preservation scope.')
        background = self._fill_readback(type('Background', (), {'Fill': native.CharBackFill})())
        if background['type_code'] != 0:
            refuse('Character background fills require a separate preservation workflow.')
        result.update(fill=fill, outline=outline, background_fill=background)
        return result

    def _text_range_state(self, document, shape):
        try:
            if (shape.Type != self.adapter.CDR_TEXT_SHAPE or shape.PowerClip is not None
                    or self._reference_count(shape.Effects)):
                refuse('Range editing requires ordinary text without clipping or effects.')
            text, story = shape.Text, shape.Text.Story
            layout = layout_readback(text, story)
            if layout['text_type_code'] not in (0, 1) or layout['frame_count'] != 1:
                refuse('Range editing requires one unfitted, unlinked text frame.')
            content = unicode_text(story.WideText)
            characters = story.Characters
            count = characters.Count
            if type(count) is not int or not 1 <= count <= MAX_NATIVE_CHARACTERS:
                refuse('Inspect at most 1024 native characters in one nonempty story.')
            native_rows, proxies, raw_parts, boundaries = [], [], [], {0: 0}
            for index in range(1, count + 1):
                native = characters.Item(index, 1)
                raw = native.WideText
                if type(raw) is not str or not 1 <= len(raw) <= MAX_CODEPOINTS:
                    refuse('Native character enumeration is empty or inconsistent.')
                start, end = native.Start, native.End
                if type(start) is not int or type(end) is not int or start > end:
                    refuse('Native character positions cannot be verified.')
                if native_rows and (start <= native_rows[-1]['start'] or end <= native_rows[-1]['end']):
                    refuse('Native character positions overlap or are not ordered.')
                raw_parts.append(raw)
                if sum(map(len, raw_parts)) > 2 * MAX_CODEPOINTS:
                    refuse('Native character enumeration exceeds the Unicode budget.')
                native_rows.append({'raw': raw, 'start': start, 'end': end,
                                    'format': self._range_format(native)})
                proxies.append(native)
                try:
                    prefix = ''.join(raw_parts).encode('utf-16-le', 'surrogatepass').decode('utf-16-le')
                except UnicodeError:
                    continue  # A high surrogate has no public boundary yet.
                boundaries[len(prefix)] = index
            if unicode_text(''.join(raw_parts)) != content or unicode_text(story.WideText) != content:
                refuse('Character enumeration does not reconstruct the exact Unicode story.')
            if characters.Count != count or len(boundaries) < 2:
                refuse('Native character count changed during inspection.')
            matrix = self._layout_method(shape, 'GetMatrix')()
            if (type(matrix) not in (tuple, list) or len(matrix) != 6
                    or any(type(value) not in (int, float) or not math.isfinite(value) for value in matrix)):
                refuse('Native text placement transform cannot be inspected.')
            identity = {'document': self._com_identity(document, strict=True),
                        'shape': self._reference_identity(shape), 'static_id': shape.StaticID,
                        'page': self._reference_identity(shape.Page), 'layer': self._reference_identity(shape.Layer),
                        'name': shape.Name, 'unit': document.Unit, 'reference_point': document.ReferencePoint,
                        'matrix_native': list(matrix)}
            state = {'content': content, 'native_rows': native_rows, 'identity': identity,
                     'text_type': layout['text_type_code'], 'frame_count': layout['frame_count']}
            state['fingerprint'] = digest(state)
            return state, boundaries, proxies
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError('CorelDRAW could not inspect a complete text range.', ErrorCode.COREL_COM_ERROR) from exc

    def _resolve_text_range(self, document, shape, start, end, state, boundaries):
        content = state['content']
        if start is None and end is None:
            selection = shape.Text.Selection
            selected = unicode_text(selection.WideText)
            matches = []
            rows = state['native_rows']
            for left, native_left in boundaries.items():
                if native_left >= len(rows) or rows[native_left]['start'] != selection.Start:
                    continue
                for right, native_right in boundaries.items():
                    if native_right > native_left and rows[native_right - 1]['end'] == selection.End and content[left:right] == selected:
                        matches.append((left, right))
            if len(matches) != 1:
                refuse('The live selected range is empty or cannot be mapped unambiguously.', ErrorCode.INVALID_ARGUMENT)
            start, end = matches[0]
        if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(content)
                or start not in boundaries or end not in boundaries
                or not safe_boundary(content, start) or not safe_boundary(content, end)):
            refuse('Supply a nonempty Unicode code-point range at safe native boundaries.', ErrorCode.INVALID_ARGUMENT)
        first, last = boundaries[start], boundaries[end]
        native = shape.Text.Story.Characters.Item(first + 1, last - first)
        if unicode_text(native.WideText) != content[start:end] or native.Characters.Count != last - first:
            refuse('The native range differs from the requested exact selected content.')
        return start, end, first, last, native

    def inspect_text_range(self, start=None, end=None, object_name='', shape_index=0, object_reference=None):
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        state, boundaries, _ = self._text_range_state(document, shape)
        start, end, first, last, _ = self._resolve_text_range(document, shape, start, end, state, boundaries)
        again, _, _ = self._text_range_state(document, shape)
        if again != state:
            refuse('Text changed during inspection; inspect again.', ErrorCode.INVALID_ARGUMENT)
        reference = self._reference_for_shape(document, shape)
        if reference is None:
            refuse('A signed stable object reference is required for range editing.')
        runs = []
        for index, row in enumerate(state['native_rows'][first:last], first + 1):
            public = {'native_index': index, 'format': row['format']}
            runs.append(public)
        return {'object_reference': reference, 'start': start, 'end': end,
                'offset_unit': 'unicode_code_points', 'selected_text': state['content'][start:end],
                'story_code_points': len(state['content']), 'native_character_count': len(state['native_rows']),
                'native_start_index': first + 1, 'native_count': last - first,
                'fingerprint': state['fingerprint'], 'character_formats': runs,
                'preservation_scope': 'installed_x7_scalar_character_properties_and_process_appearance'}

    @tracked_mutation
    def edit_text_range(self, object_reference, start, end, expected_text, expected_fingerprint,
                        replacement=None, font=None, size_points=None, bold=None, italic=None, underline=None):
        if type(expected_fingerprint) is not str or not re.fullmatch('[0-9a-f]{64}', expected_fingerprint):
            refuse('Supply the fingerprint returned by inspect_text_range.', ErrorCode.INVALID_ARGUMENT)
        if type(expected_text) is not str or not expected_text or len(expected_text) > MAX_CODEPOINTS:
            refuse('Supply the exact previously inspected selected text.', ErrorCode.INVALID_ARGUMENT)
        if replacement is not None and (type(replacement) is not str or not replacement
                or unicode_text(replacement) != replacement or any(c in replacement for c in '\r\n\t')):
            refuse('Replacement must be nonempty Unicode text without paragraph breaks or tabs.', ErrorCode.INVALID_ARGUMENT)
        values = (font, size_points, bold, italic, underline)
        requested = validate_style(*values) if any(v is not None for v in values) else {}
        if not requested and replacement is None:
            refuse('Supply replacement text or character formatting.', ErrorCode.INVALID_ARGUMENT)
        if replacement is not None and requested:
            refuse('Inspect again between replacement and formatting operations.', ErrorCode.INVALID_ARGUMENT)
        document = self._selector_document('', 0, object_reference)
        shape, _ = self._resolve_object_reference(document, object_reference)
        before, boundaries, _ = self._text_range_state(document, shape)
        if before['fingerprint'] != expected_fingerprint:
            refuse('Text, formatting or object location changed; inspect again.', ErrorCode.INVALID_ARGUMENT)
        start, end, first, last, native = self._resolve_text_range(document, shape, start, end, before, boundaries)
        if before['content'][start:end] != expected_text:
            refuse('Selected content differs from expected_text; no edit was applied.', ErrorCode.INVALID_ARGUMENT)
        selected_formats = [row['format'] for row in before['native_rows'][first:last]]
        if replacement is not None and (any(c in expected_text for c in '\r\n\t')
                or any(value != selected_formats[0] for value in selected_formats)):
            refuse('Replacement requires uniform selected formatting and no paragraph breaks or tabs.')
        if replacement is not None:
            candidate = before['content'][:start] + replacement + before['content'][end:]
            if (len(candidate.encode('utf-16-le')) // 2 > MAX_NATIVE_CHARACTERS
                    or not safe_boundary(candidate, start) or not safe_boundary(candidate, start + len(replacement))):
                refuse('Replacement exceeds the native budget or joins a protected Unicode sequence.', ErrorCode.INVALID_ARGUMENT)
        if font is not None:
            requested['font'] = self._require_font(font)
        if size_points is not None:
            requested['size_points'] = struct.unpack('<f', struct.pack('<f', size_points))[0]
        current, _, _ = self._text_range_state(document, shape)
        if current != before:
            refuse('Text changed during preflight; inspect again.', ErrorCode.INVALID_ARGUMENT)
        expected = copy.deepcopy(before)
        try:
            for field, value in requested.items():
                current, current_boundaries, _ = self._text_range_state(document, shape)
                if current != expected:
                    refuse('Concurrent text changes detected; remaining writes stopped.', ErrorCode.INVALID_ARGUMENT)
                _, _, _, _, native = self._resolve_text_range(document, shape, start, end, current, current_boundaries)
                attr = STYLE_ATTRIBUTES[field]
                native_value = UNDERLINES[value] if field == 'underline' else value
                self._note_mutation()
                setattr(native, attr, native_value)
                actual, _, _ = self._text_range_state(document, shape)
                for index, row in enumerate(expected['native_rows'][first:last], first):
                    row['format'][attr] = native_value
                    if field in ('font', 'bold', 'italic', 'underline'):
                        row['format']['Style'] = actual['native_rows'][index]['format']['Style']
                expected.pop('fingerprint')
                expected['fingerprint'] = digest(expected)
                if actual != expected:
                    refuse('Formatting readback or surrounding preservation failed.', ErrorCode.COREL_COM_ERROR)
            if replacement is not None:
                self._note_mutation()
                native.WideText = replacement
                actual, after_boundaries, _ = self._text_range_state(document, shape)
                expected_content = before['content'][:start] + replacement + before['content'][end:]
                suffix_index = after_boundaries.get(start + len(replacement))
                if actual['content'] != expected_content or start not in after_boundaries or suffix_index is None:
                    refuse('Replacement Unicode readback differs from the request.', ErrorCode.COREL_COM_ERROR)
                replacement_first = after_boundaries[start]
                # Native positions after the replacement shift; compare exact
                # surrounding raw content and formatting, excluding positions.
                project = lambda rows: [(r['raw'], r['format']) for r in rows]
                if (project(actual['native_rows'][:replacement_first]) != project(before['native_rows'][:first])
                        or project(actual['native_rows'][suffix_index:]) != project(before['native_rows'][last:])
                        or any(r['format'] != selected_formats[0] for r in actual['native_rows'][replacement_first:suffix_index])
                        or actual['identity'] != before['identity']
                        or actual['text_type'] != before['text_type'] or actual['frame_count'] != before['frame_count']):
                    refuse('Replacement formatting or surrounding text changed.', ErrorCode.COREL_COM_ERROR)
            else:
                actual = expected
            shape, reference = self._resolve_object_reference(document, object_reference)
            final, _, _ = self._text_range_state(document, shape)
            if final != actual:
                refuse('Text changed during final target reconciliation.', ErrorCode.COREL_COM_ERROR)
            return {'updated': True, 'object_reference': reference, 'start': start,
                    'end': start + len(replacement) if replacement is not None else end,
                    'selected_text': replacement if replacement is not None else expected_text,
                    'fingerprint': actual['fingerprint'], 'surrounding_text_preserved': True,
                    'surrounding_formatting_preserved': True, 'requested_style': requested,
                    'preservation_scope': 'installed_x7_scalar_character_properties_and_process_appearance'}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError('CorelDRAW could not complete the text-range edit; inspect partial changes.',
                                   ErrorCode.COREL_COM_ERROR) from exc
