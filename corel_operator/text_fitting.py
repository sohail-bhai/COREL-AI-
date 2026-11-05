"""Bounded source-preserving paragraph fitting using native font/overflow readback."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import struct

from .errors import CorelBridgeError, ErrorCode
from .gradient_bridge import complete_process_readback
from .native_tracking import tracked_mutation
from .powerclip_bridge import validate_name
from .typography import finite_number, layout_readback, read_property, spacing_readback, style_readback

MAX_FIT_PROBES = 24


def upward_single(value):
    """X7 TextRange.Size is Single: round toward readability, never below a bound."""
    bits = struct.unpack('<I', struct.pack('<f', value))[0]
    observed = struct.unpack('<f', struct.pack('<I', bits))[0]
    return struct.unpack('<f', struct.pack('<I', bits + (observed < value)))[0]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def ordinary_appearance(fill, outline):
    return (fill['type_code'] in (0, 1) and (fill['type_code'] == 0 or complete_process_readback(fill['color']))
            and outline['type_code'] in (0, 1) and (outline['type_code'] == 0 or
                complete_process_readback(outline['color']) and type(outline['width_raw']) in (int, float)
                and math.isfinite(outline['width_raw']) and outline['width_raw'] > 0))


class TextFittingMixin:
    def _fitting_state(self, document, shape):
        try:
            if shape.Type != self.adapter.CDR_TEXT_SHAPE or shape.PowerClip is not None or self._reference_count(shape.Effects):
                raise CorelBridgeError('Fitting requires ordinary text without effects or clipping.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            text, story = shape.Text, shape.Text.Story
            layout = layout_readback(text, story)
            if layout['text_type_code'] != 1 or layout['frame_count'] != 1 or type(layout['overflow']) is not bool:
                raise CorelBridgeError('Fitting requires one unfitted, unlinked paragraph frame with known overflow.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            frame = text.Frame
            if (frame.IsInsideContainer is not False or frame.IsFittedToPath is not False
                    or not self._same_com_object(frame.FrameShape, shape, strict=True)):
                raise CorelBridgeError('Container/path fitting and ambiguous frame ownership require a separate workflow.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            style = style_readback(story)
            if style['unavailable_or_mixed_properties'] or not 1 <= style['size_points'] <= 500:
                raise CorelBridgeError('Fitting requires readable uniform basic styling at 1–500 points.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            content = story.Text
            if type(content) is not str or not content.strip() or len(content) > 10000:
                raise CorelBridgeError('Fitting requires nonblank text within 10000 characters.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            spacing = spacing_readback(story)
            horizontal = {key: read_property(story, key, 'number') for key in ('CharSpacing', 'WordSpacing')}
            if (any(value is None for value in spacing.values()) or any(value is None for value in horizontal.values())
                    or spacing['line_spacing'] <= 0 or spacing['paragraph_before'] < 0 or spacing['paragraph_after'] < 0):
                raise CorelBridgeError('Spacing preservation is unavailable or mixed.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            tree, _ = self._clip_tree(document, shape)
            if tree['name_truncated']:
                raise CorelBridgeError('Paragraph names exceed exact preservation scope.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            tree['text'].pop('preview', None)
            frame_state = {'vertical_alignment_code': frame.VerticalAlignment, 'column_count': frame.ColumnCount,
                           'fill': self._fill_readback(frame), 'outline': self._outline_readback(frame)}
            if (type(frame_state['vertical_alignment_code']) is not int
                    or type(frame_state['column_count']) is not int or not 1 <= frame_state['column_count'] <= 20):
                raise CorelBridgeError('Frame layout metadata is unavailable or exceeds 20 columns.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            width_method = self._layout_method(frame, 'ColumnWidth')
            gutter_method = self._layout_method(frame, 'ColumnGutter') if frame_state['column_count'] > 1 else None
            frame_state['columns_native'] = []
            for index in range(1, frame_state['column_count'] + 1):
                width = width_method(index)
                gutter = gutter_method(index) if index < frame_state['column_count'] else None
                if (type(width) not in (int, float) or not math.isfinite(width) or width <= 0
                        or index < frame_state['column_count'] and gutter is None
                        or gutter is not None and (type(gutter) not in (int, float) or not math.isfinite(gutter) or gutter < 0)):
                    raise CorelBridgeError('Native frame column dimensions are invalid.', ErrorCode.UNSUPPORTED_IN_PROFILE)
                frame_state['columns_native'].append({'width_raw': width, 'following_gutter_raw': gutter})
            frame_state['column_read_unit_code'] = document.Unit
            transparency = tree['transparency']
            if (not ordinary_appearance(tree['fill'], tree['outline']) or not ordinary_appearance(frame_state['fill'], frame_state['outline'])
                    or not transparency['available'] or transparency['type_code'] not in (0, 1)
                    or transparency['type_code'] == 1 and any(transparency[k] is None
                        for k in ('uniform_percent', 'applied_to_code', 'merge_mode_code'))):
                raise CorelBridgeError('Paragraph/frame appearance preservation is incomplete or unsupported.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            return {'tree': tree, 'style': style, 'spacing': spacing, 'horizontal': horizontal,
                    'layout': layout, 'frame': frame_state}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError('Native paragraph fitting metadata could not be inspected.', ErrorCode.UNSUPPORTED_IN_PROFILE) from exc

    def _fitting_equivalent(self, original, actual, allow_size=False, allowed_names=None):
        left, right = copy.deepcopy(original), copy.deepcopy(actual)
        for value in (left, right):
            for field in ('identity', 'static_id', 'name_sha256', 'object_name', 'name_truncated'):
                value['tree'].pop(field, None)
        if allowed_names is not None and actual['tree']['object_name'] not in allowed_names:
            return False
        if allow_size:
            for value in (left, right):
                value['style'].pop('size_points')
                value['tree']['text'].pop('size_points')
                value['layout'].pop('overflow')
        return left == right

    @tracked_mutation
    def fit_paragraph_text(self, object_reference, minimum_size_points=8., size_tolerance_points=.1, result_name=''):
        minimum = finite_number(minimum_size_points, 'minimum_size_points', 1, 500)
        tolerance = finite_number(size_tolerance_points, 'size_tolerance_points', .01, 1)
        validate_name(result_name)
        document, sources = self._clip_inputs([object_reference])
        source = sources[0]
        before = self._fitting_state(document, source)
        original_size = before['style']['size_points']
        if minimum > original_size:
            raise CorelBridgeError('Minimum size exceeds the current paragraph size; fitting never enlarges text.', ErrorCode.INVALID_ARGUMENT)
        layer, page = source.Layer, document.ActivePage
        baseline, baseline_nodes = self._clip_baseline(document, layer)
        if len(baseline_nodes) >= 1000:
            raise CorelBridgeError('Original and copied ownership exceed 1000 shapes.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        state = {'page': page, 'layer': layer, 'baseline_ids': set(baseline_nodes),
                 'baseline_curves': {self._reference_identity(s.Curve) for s in baseline_nodes.values() if s.Type == 3},
                 'baseline_stories': {self._reference_identity(s.Text.Story) for s in baseline_nodes.values() if s.Type == 6},
                 'owned': {}, 'owned_curves': {}, 'owned_stories': {}, 'ownership_uncertain': False}
        name = self._unique_name(document, result_name, 'AI_FittedParagraph')
        if self._fitting_state(document, source) != before:
            raise CorelBridgeError('Source changed during fitting preflight; inspect again.', ErrorCode.INVALID_ARGUMENT)
        group = 'not_started'
        output = None
        attempted_sizes = {original_size}
        probes = []
        source_hash = digest(before)

        def sources_match():
            self._target_document()
            resolved, _ = self._resolve_object_reference(document, object_reference, mutation=True)
            if not self._same_com_object(resolved, source, strict=True):
                return False
            return self._fitting_state(document, source) == before

        def probe(size):
            if len(probes) >= MAX_FIT_PROBES:
                raise CorelBridgeError('Fitting exceeded its 24-probe bound.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            size = upward_single(size)
            if not minimum <= size <= original_size:
                raise CorelBridgeError('No native font-size candidate satisfies the requested bounds.', ErrorCode.INVALID_ARGUMENT)
            attempted_sizes.add(size)
            self._note_mutation()
            output.Text.Story.Size = size
            actual = self._fitting_state(document, output)
            observed = actual['style']['size_points']
            if (not minimum <= observed <= original_size or not math.isclose(observed, size, abs_tol=.01, rel_tol=0)
                    or not self._fitting_equivalent(before, actual, allow_size=True)):
                raise CorelBridgeError('Font fitting changed preserved state or violated size bounds.', ErrorCode.COREL_COM_ERROR)
            probes.append({'requested_size_points': size, 'actual_size_points': observed, 'overflow': actual['layout']['overflow']})
            if not sources_match():
                raise CorelBridgeError('Source changed during fitting; original edits will be preserved.', ErrorCode.COREL_COM_ERROR)
            return actual

        try:
            group = 'opening'
            self._note_mutation()
            document.BeginCommandGroup('AI Editable Paragraph Fitting')
            group = 'open'
            output = self._clip_clone(document, source, state)
            copied = self._fitting_state(document, output)
            if not self._fitting_equivalent(before, copied) or not sources_match():
                raise CorelBridgeError('Independent paragraph copy differs from the source snapshot.', ErrorCode.COREL_COM_ERROR)
            actual = copied
            if copied['layout']['overflow']:
                low = upward_single(minimum)
                if low > original_size:
                    raise CorelBridgeError('No representable size fits within the requested range.', ErrorCode.INVALID_ARGUMENT)
                actual = probe(low)
                if actual['layout']['overflow']:
                    raise CorelBridgeError('Paragraph still overflows at the minimum readable size.', ErrorCode.INVALID_ARGUMENT)
                high = original_size
                while high - low > tolerance:
                    middle = upward_single((low + high) / 2)
                    if not low < middle < high:
                        break
                    candidate = probe(middle)
                    if candidate['layout']['overflow']:
                        high = middle
                    else:
                        low, actual = middle, candidate
                actual = probe(low)
            self._note_mutation()
            output.Name = name
            actual = self._fitting_state(document, output)
            if (output.Name != name or actual['layout']['overflow'] or not self._fitting_equivalent(before, actual, allow_size=True)
                    or not minimum <= actual['style']['size_points'] <= original_size):
                raise CorelBridgeError('Final editable fitting result failed preservation/readback.', ErrorCode.COREL_COM_ERROR)
            output_key = self._reference_identity(output)
            roots, nodes = self._clip_baseline(document, layer)
            if (set(roots) != set(baseline) | {output_key} or [key for key in roots if key in baseline] != baseline
                    or set(nodes) != state['baseline_ids'] | {output_key} or not sources_match()):
                raise CorelBridgeError('Fitting changed original membership/order or source state.', ErrorCode.COREL_COM_ERROR)
            reference = self._reference_for_shape(document, output)
            if reference is None:
                raise CorelBridgeError('Fitted output lacks complete signed identity.', ErrorCode.COREL_COM_ERROR)
            _, _, identity = self._inspection_target('', 0, reference)
            bounds = self._typography_bounds(document, output)
            receipt = digest(actual)
            group = 'closing'
            document.EndCommandGroup()
            group = 'closed'
            final_roots, final_nodes = self._clip_baseline(document, layer)
            if (digest(self._fitting_state(document, output)) != receipt or not sources_match()
                    or set(final_roots) != set(baseline) | {output_key}
                    or [key for key in final_roots if key in baseline] != baseline
                    or set(final_nodes) != state['baseline_ids'] | {output_key}):
                raise CorelBridgeError('Source/output changed during final fitting observation.', ErrorCode.COREL_COM_ERROR)
            return {'created': True, 'object': identity, 'actual_bounds_inches': bounds,
                    'original_size_points': original_size, 'minimum_size_points': minimum,
                    'actual_size_points': actual['style']['size_points'], 'overflow': False,
                    'probe_count': len(probes), 'probes': probes, 'size_tolerance_points': tolerance,
                    'search_scope': 'largest_verified_probe_under_bounded_overflow_search',
                    'content_sha256': before['tree']['text']['content_sha256'],
                    'source_preservation': {'verified': True, 'scope': 'root_membership_relative_order_measured_source_text_frame_basic_appearance',
                                            'source_sha256': source_hash},
                    'verification_status': 'implemented_unverified',
                    'warnings': ['Native story overflow does not prove glyph/safe-area/visual fit or global font-size optimality.']}
        except Exception as exc:
            rollback = {'attempted': True, 'verified': False, 'output_removed': False, 'output_retained': False,
                        'command_group_uncertain': group in ('opening', 'closing')}
            try:
                # Inspect ownership and state before deleting; preserve concurrent edits.
                roots, _ = self._clip_baseline(document, layer)
                for key, owned in list(state['owned'].items()):
                    if key not in roots:
                        state['ownership_uncertain'] = True
                        rollback['output_retained'] = True
                        continue
                    if key in roots and key not in state['baseline_ids']:
                        current = self._fitting_state(document, owned)
                        _, descendants = self._clip_tree(document, owned, properties=False)
                        known_size = current['style']['size_points'] in attempted_sizes
                        story_independent = self._reference_identity(owned.Text.Story) not in state['baseline_stories']
                        if not story_independent:
                            state['ownership_uncertain'] = True
                        if (set(descendants) == {key} and self._same_com_object(owned.Page, page, strict=True)
                                and self._same_com_object(owned.Layer, layer, strict=True) and known_size and story_independent
                                and self._fitting_equivalent(before, current, allow_size=True,
                                    allowed_names={before['tree']['object_name'], name})):
                            self._note_mutation()
                            owned.Delete()
                            rollback['output_removed'] = True
                        else:
                            rollback['output_retained'] = True
                if group == 'open':
                    group = 'closing'
                    document.EndCommandGroup()
                    group = 'closed'
                roots, nodes = self._clip_baseline(document, layer)
                rollback['output_retained'] |= bool(set(roots) - set(baseline))
                rollback['verified'] = (roots == baseline and set(nodes) == state['baseline_ids'] and sources_match()
                                        and not state['ownership_uncertain'] and group in ('closed', 'not_started'))
            except Exception as cleanup:
                rollback['error_type'] = type(cleanup).__name__
                try:
                    rollback['output_retained'] = bool(set(self._vector_layer_members(layer)) - set(baseline))
                except Exception:
                    rollback['output_retained'] = True
            rollback['command_group_uncertain'] = group in ('opening', 'closing')
            raise CorelBridgeError('Editable paragraph fitting could not complete safely. ' +
                ('Owned output was discarded and measured source verified.' if rollback['verified'] else 'Inspect exact source/output state before recovery.'),
                exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                {'rollback': rollback, 'ownership_uncertain': state['ownership_uncertain'],
                 'fitting_failure': str(exc)[:400] if isinstance(exc, CorelBridgeError) else 'Native call or readback failed.'}) from exc
