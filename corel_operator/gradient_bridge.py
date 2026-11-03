"""Bounded fountain-fill inspection and fingerprint-guarded opaque gradients."""
from __future__ import annotations

import math

from .appearance_bridge import validate_process_color
from .errors import CorelBridgeError, ErrorCode
from .native_tracking import tracked_mutation
from .vector_geometry import seal

MAX_GRADIENT_STOPS = 32


def complete_process_readback(color):
    try:
        requested, _ = validate_process_color({'model': color['model'], **color['value']})
        return color['type_code'] == (5 if requested['model'] == 'rgb' else 2)
    except (CorelBridgeError, TypeError, KeyError):
        return False


def validate_gradient_stops(stops):
    if type(stops) is not list or not 2 <= len(stops) <= MAX_GRADIENT_STOPS:
        raise CorelBridgeError('Supply 2-32 ordered gradient stops including 0 and 100 percent.', ErrorCode.INVALID_ARGUMENT)
    result = []
    for stop in stops:
        if type(stop) is not dict or set(stop) != {'position_percent', 'color'}:
            raise CorelBridgeError('Each stop requires exactly position_percent and color.', ErrorCode.INVALID_ARGUMENT)
        position = stop['position_percent']
        if type(position) is not int or not 0 <= position <= 100:
            raise CorelBridgeError('Stop positions must be integer percentages 0-100.', ErrorCode.INVALID_ARGUMENT)
        color, components = validate_process_color(stop['color'])
        result.append((position, color, components))
    positions = [s[0] for s in result]
    if positions[0] != 0 or positions[-1] != 100 or any(a >= b for a, b in zip(positions, positions[1:])):
        raise CorelBridgeError('Stops must be strictly increasing from 0 to 100 percent.', ErrorCode.INVALID_ARGUMENT)
    if len({s[1]['model'] for s in result}) != 1:
        raise CorelBridgeError('All gradient stops must use one RGB or CMYK process model.', ErrorCode.INVALID_ARGUMENT)
    return result


class GradientBridgeMixin:
    def _gradient_geometry(self, document, shape):
        geometry = self._process_color_geometry(document, shape)
        if shape.Type == self.adapter.CDR_TEXT_SHAPE:
            text = geometry['text']
            if not text['font'] or len(text['font']) > 256 or not math.isfinite(text['size_points']) or text['size_points'] <= 0 or type(text['bold']) is not bool:
                raise CorelBridgeError('Gradient text edits require readable whole-story font, size and bold formatting.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            try:
                text_type = shape.Text.Type
                frame_count = self._reference_count(shape.Text.Frames) if text_type == 1 else None
            except Exception as exc:
                raise CorelBridgeError('Gradient text subtype/frame metadata is unavailable.', ErrorCode.UNSUPPORTED_IN_PROFILE) from exc
            if type(text_type) is not int or text_type not in (0, 1) or text_type == 1 and frame_count != 1:
                raise CorelBridgeError('Gradient text edits support artistic or unlinked paragraph stories.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            geometry['text_type_code'] = text_type
            geometry['frame_count'] = frame_count
        return geometry

    def _gradient_state(self, document, shape):
        unavailable = []

        def read(owner, name, kind, low=None, high=None):
            try:
                value = getattr(owner, name)
                valid = type(value) is kind if kind in (int, bool) else type(value) in (int, float) and math.isfinite(value)
                if valid and low is not None:
                    valid = low <= value <= high
                if valid:
                    return float(value) if kind is float else value
            except Exception:
                pass
            unavailable.append(name)
            return None

        try:
            fill = shape.Fill
        except Exception:
            fill = None
        code = read(fill, 'Type', int)
        state = {'fill_available': fill is not None, 'fill_type_code': code,
                 'fill_type': self.adapter.FILL_TYPE_NAMES.get(code, 'unknown'),
                 'gradient': None, 'complete': False, 'unavailable_properties': unavailable}
        if code != 2:
            state['complete'] = fill is not None and code in self.adapter.FILL_TYPE_NAMES
            return state
        try:
            native = fill.Fountain
        except Exception:
            native = None
            unavailable.append('Fountain')
        kind = read(native, 'Type', int)
        gradient = {
            'type_code': kind, 'type': {v: k for k, v in self.adapter.GRADIENT_TYPE_CODES.items()}.get(kind, 'unknown'),
            'angle_degrees': read(native, 'Angle', float),
            'steps': read(native, 'Steps', int, 0, 256),
            'edge_padding_percent': read(native, 'EdgePad', int, 0, 100),
            'midpoint_percent': read(native, 'MidPoint', int, 0, 100),
            'blend_type_code': read(native, 'BlendType', int),
            'center_offset_x_percent': read(native, 'CenterOffsetX', float),
            'center_offset_y_percent': read(native, 'CenterOffsetY', float),
            'smooth_blend': read(native, 'SmoothBlend', bool),
            'spread_method_code': read(native, 'SpreadMethod', int),
            'anisotropic': read(native, 'Anisotropic', bool),
            'is_transparent': read(native, 'IsTransparent', bool),
            'merge_mode_code': read(native, 'MergeMode', int),
            'blend_acceleration': read(native, 'BlendAcceleration', float),
            'has_hsb_blends': read(native, 'HasHSBBlends', bool),
            'has_non_linear_blends': read(native, 'HasNonLinearBlends', bool),
            'transform': {name: read(native, name, float) for name in ('ScaleX', 'ScaleY', 'Skew')},
            'coordinates_inches': {}, 'stops': [], 'native_stop_count': None,
        }
        state['gradient'] = gradient
        with self._in_inches(document, strict_restore=True):
            gradient['coordinates_inches'] = {name: read(native, name, float) for name in ('StartX', 'StartY', 'EndX', 'EndY', 'End2X', 'End2Y')}
        try:
            colors = native.Colors
        except Exception:
            colors = None
            unavailable.append('Colors')
        count = read(colors, 'Count', int)
        gradient['native_stop_count'] = count
        if count is None or not 2 <= count <= MAX_GRADIENT_STOPS:
            unavailable.append('bounded_endpoint_inclusive_stop_collection')
        else:
            for index in range(1, count + 1):
                try:
                    item = self._collection_item(colors, index)
                    color = self._color_readback(item.Color)
                except Exception:
                    item, color = None, None
                if not complete_process_readback(color):
                    unavailable.append('StopColor')
                gradient['stops'].append({
                    'position_percent': read(item, 'Position', int, 0, 100), 'color': color,
                    'midpoint_percent': read(item, 'MidPoint', int, 0, 100),
                    'blend_type_code': read(item, 'BlendType', int),
                    'opacity_raw': read(item, 'Opacity', int, 0, 255),
                })
            positions = [s['position_percent'] for s in gradient['stops']]
            if None in positions or positions[0] != 0 or positions[-1] != 100 or any(a >= b for a, b in zip(positions, positions[1:])):
                unavailable.append('ordered_endpoint_inclusive_stop_collection')
            for name, stop in (('StartColor', gradient['stops'][0]), ('EndColor', gradient['stops'][-1])):
                try:
                    actual = self._color_readback(getattr(native, name))
                except Exception:
                    actual = None
                if actual is None or actual != stop['color']:
                    unavailable.append(name)
        state['unavailable_properties'] = sorted(set(unavailable))
        state['complete'] = not unavailable and kind in self.adapter.GRADIENT_TYPE_CODES.values()
        return state

    def _gradient_fingerprint(self, document, shape, state):
        if not state['complete']:
            return None
        return seal({'schema': 'gradient-fill-v1', 'document_session_id': self._document_session_id(document),
                     'shape_identity': self._reference_identity(shape), 'state': state,
                     'base_fill': self._fill_readback(shape)})['fingerprint']

    def get_gradient_fill(self, object_name='', shape_index=0, object_reference=None):
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        state = self._gradient_state(document, shape)
        return {'object': identity, 'fill': state, 'fingerprint': self._gradient_fingerprint(document, shape, state),
                'verification_status': 'implemented_unverified',
                'warnings': ['Stop opacity is raw native metadata; rendered interpolation, ICC conversion and printed appearance require consolidated/manual verification.']}

    @tracked_mutation
    def set_gradient_fill(self, stops, gradient_type='linear', angle_degrees=0., steps=0, edge_padding_percent=0,
                          center_offset_x_percent=0., center_offset_y_percent=0., replace_existing=False,
                          expected_fingerprint='', object_name='', shape_index=0, object_reference=None):
        requested = validate_gradient_stops(stops)
        if type(gradient_type) is not str or gradient_type not in self.adapter.GRADIENT_TYPE_CODES:
            raise CorelBridgeError('gradient_type must be linear, radial, conical or square.', ErrorCode.INVALID_ARGUMENT)
        for name, value, low, high in (('angle_degrees', angle_degrees, -360., 360.),
                                      ('center_offset_x_percent', center_offset_x_percent, -50., 50.),
                                      ('center_offset_y_percent', center_offset_y_percent, -50., 50.)):
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise CorelBridgeError(f'{name} must be finite in [{low}, {high}].', ErrorCode.INVALID_ARGUMENT)
        if type(steps) is not int or steps != 0 and not 2 <= steps <= 256:
            raise CorelBridgeError('steps must be 0 (automatic) or an integer 2-256.', ErrorCode.INVALID_ARGUMENT)
        if type(edge_padding_percent) is not int or not 0 <= edge_padding_percent <= 49:
            raise CorelBridgeError('edge_padding_percent must be an integer 0-49.', ErrorCode.INVALID_ARGUMENT)
        if type(replace_existing) is not bool or type(expected_fingerprint) is not str:
            raise CorelBridgeError('replace_existing must be boolean and expected_fingerprint a string.', ErrorCode.INVALID_ARGUMENT)
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        reference = identity['object_reference']
        if reference is None:
            raise CorelBridgeError('Gradient edits require complete native identity.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        self._resolve_object_reference(document, reference, mutation=True)
        geometry = self._gradient_geometry(document, shape)
        before = self._gradient_state(document, shape)
        fingerprint = self._gradient_fingerprint(document, shape, before)
        if not before['complete']:
            raise CorelBridgeError('Native fill or bounded gradient metadata is unavailable; inspect the target before editing.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if (before['fill_type_code'] == 2 and not expected_fingerprint) or (expected_fingerprint and expected_fingerprint != fingerprint):
            raise CorelBridgeError('Gradient revisions require the current inspection fingerprint.', ErrorCode.INVALID_ARGUMENT)
        if before['fill_type_code'] not in (0, 1, 2) and not replace_existing:
            raise CorelBridgeError('Replacing another non-uniform fill requires replace_existing=true.', ErrorCode.INVALID_ARGUMENT)
        outline = self._outline_readback(shape)
        if outline['type_code'] not in (0, 1) or (outline['type_code'] == 1 and (not complete_process_readback(outline['color']) or
                type(outline['width_raw']) not in (int, float) or not math.isfinite(outline['width_raw']) or outline['width_raw'] <= 0)):
            raise CorelBridgeError('Gradient edits require no outline or a readable ordinary process-color outline.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        transparency = self._transparency_readback(shape)
        if not transparency['available'] or transparency['type_code'] not in (0, 1):
            raise CorelBridgeError('Gradient edits currently support no transparency or fully readable uniform transparency.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if transparency['type_code'] == 1 and any(transparency[k] is None for k in ('uniform_percent', 'applied_to_code', 'merge_mode_code')):
            raise CorelBridgeError('Uniform transparency metadata is incomplete.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        apply = self._layout_method(shape.Fill, 'ApplyFountainFill')
        prepared = []
        for _, color, components in requested:
            factory = self._layout_method(self.app, 'CreateRGBColor' if color['model'] == 'rgb' else 'CreateCMYKColor')
            try:
                native_color = factory(*components)
            except Exception as exc:
                raise CorelBridgeError('Could not prepare a native gradient color.', ErrorCode.COREL_COM_ERROR) from exc
            prepared.append(native_color)
        for (_, color, _), native_color in zip(requested, prepared):
            actual = self._color_readback(native_color)
            if not actual or actual['model'] != color['model'] or actual['value'] != {k: v for k, v in color.items() if k != 'model'}:
                raise CorelBridgeError('Native color factories did not retain independent requested process components.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        angle = angle_degrees % 360.
        try:
            self._note_mutation()
            apply(prepared[0], prepared[-1], self.adapter.GRADIENT_TYPE_CODES[gradient_type], angle, steps,
                  edge_padding_percent, 50, self.adapter.CDR_DIRECT_FOUNTAIN_BLEND, center_offset_x_percent, center_offset_y_percent)
            native = shape.Fill.Fountain
            colors = native.Colors
            if self._reference_count(colors) != 2:
                raise CorelBridgeError('Native gradient creation did not yield exactly two endpoint stops.', ErrorCode.COREL_COM_ERROR)
            add = self._layout_method(colors, 'Add')
            for (position, _, _), native_color in zip(requested[1:-1], prepared[1:-1]):
                self._note_mutation()
                add(native_color, position)
            if self._reference_count(colors) != len(requested):
                raise CorelBridgeError('Native gradient stop count differs from the requested stops.', ErrorCode.COREL_COM_ERROR)
            for index in range(1, len(requested) + 1):
                item = self._collection_item(colors, index)
                self._note_mutation(); item.MidPoint = 50
                self._note_mutation(); item.BlendType = self.adapter.CDR_DIRECT_FOUNTAIN_BLEND
            for name, value in (('SmoothBlend', True), ('SpreadMethod', self.adapter.CDR_FOUNTAIN_SPREAD_PAD),
                                ('Anisotropic', False), ('MergeMode', self.adapter.CDR_MERGE_NORMAL), ('BlendAcceleration', 0.)):
                self._note_mutation()
                setattr(native, name, value)
            self._note_mutation()
            self._layout_method(native, 'MakeOpaque')()
            after = self._gradient_state(document, shape)
            actual = after['gradient']
            valid = after['complete'] and actual['native_stop_count'] == len(requested) and actual['type'] == gradient_type and actual['steps'] == steps and actual['edge_padding_percent'] == edge_padding_percent
            if valid:
                valid = abs((actual['angle_degrees'] - angle + 180.) % 360. - 180.) <= 1e-7
                valid = valid and math.isclose(actual['center_offset_x_percent'], center_offset_x_percent, abs_tol=1e-7)
                valid = valid and math.isclose(actual['center_offset_y_percent'], center_offset_y_percent, abs_tol=1e-7)
                valid = valid and actual['smooth_blend'] is True and actual['spread_method_code'] == self.adapter.CDR_FOUNTAIN_SPREAD_PAD
                valid = valid and actual['anisotropic'] is False and actual['is_transparent'] is False and actual['merge_mode_code'] == self.adapter.CDR_MERGE_NORMAL
                valid = valid and actual['blend_acceleration'] == 0 and actual['has_hsb_blends'] is False and actual['has_non_linear_blends'] is False
                valid = valid and actual['blend_type_code'] in (self.adapter.CDR_DIRECT_FOUNTAIN_BLEND, self.adapter.CDR_CUSTOM_FOUNTAIN_BLEND)
                for (position, color, _), stop in zip(requested, actual['stops']):
                    valid = valid and stop['position_percent'] == position and stop['color']['model'] == color['model']
                    valid = valid and stop['color']['value'] == {k: v for k, v in color.items() if k != 'model'}
                    valid = valid and stop['midpoint_percent'] == 50 and stop['blend_type_code'] == self.adapter.CDR_DIRECT_FOUNTAIN_BLEND
            self._resolve_object_reference(document, reference, mutation=True)
            if not valid or geometry != self._gradient_geometry(document, shape) or outline != self._outline_readback(shape) or transparency != self._transparency_readback(shape):
                raise CorelBridgeError('Native gradient or measured geometry/other appearance channels differ from the request.', ErrorCode.COREL_COM_ERROR)
            return {'updated': True, 'object': identity, 'before_fingerprint': fingerprint,
                    'fill': after, 'fingerprint': self._gradient_fingerprint(document, shape, after),
                    'preservation_verified': True, 'verification_status': 'implemented_unverified',
                    'warnings': ['Opaque direct process-color gradients only; rendered interpolation, ICC/print behavior and native coordinate semantics require consolidated/manual verification.']}
        except Exception as exc:
            raise CorelBridgeError('Gradient assignment did not complete with verified native state. Inspect the target and reconcile before further edits.',
                                   exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                                   {'rollback': {'attempted': False, 'verified': False}, 'recovery_required': True}) from exc
