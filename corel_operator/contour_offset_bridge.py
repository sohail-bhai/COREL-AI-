"""Native contour derivatives with copied sources and explicit tree ownership."""
from __future__ import annotations

import math

from .appearance_bridge import validate_process_color
from .errors import CorelBridgeError, ErrorCode
from .gradient_bridge import complete_process_readback
from .native_tracking import tracked_mutation
from .powerclip_bridge import validate_name
from .vector_geometry import paths_equivalent, paths_match

MAX_OFFSET_SHAPES = 1000
MAX_OFFSET_DEPTH = 32
MAX_OFFSET_OUTPUTS = 64
MAX_OFFSET_NODES = 16384


class ContourOffsetBridgeMixin:
    def _offset_tree(self, shape, nodes=None, depth=0):
        nodes = {} if nodes is None else nodes
        key = self._reference_identity(shape)
        if key in nodes or len(nodes) >= MAX_OFFSET_SHAPES or depth > MAX_OFFSET_DEPTH:
            raise CorelBridgeError('Contour ownership exceeds 1000 shapes/32 levels or contains aliases.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if type(shape.Type) is not int or shape.Type not in (*self.adapter.VECTOR_PRIMITIVE_TYPES, 5, 6, 7, self.adapter.CDR_CONTOUR_GROUP_SHAPE):
            raise CorelBridgeError('Contour ownership cannot account for this native object type.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        nodes[key] = shape
        try:
            clip = shape.PowerClip
            if clip is not None and not self._same_com_object(clip.Parent, shape, strict=True):
                raise CorelBridgeError('Clipped descendant ownership is inconsistent.', ErrorCode.COREL_COM_ERROR)
            collections = [shape.Shapes] if shape.Type in (7, self.adapter.CDR_CONTOUR_GROUP_SHAPE) else []
            if clip is not None:
                collections.append(clip.Shapes)
            for collection in collections:
                count = self._reference_count(collection)
                if count > MAX_OFFSET_SHAPES - len(nodes):
                    raise CorelBridgeError('Contour descendant membership exceeds the ownership budget.', ErrorCode.UNSUPPORTED_IN_PROFILE)
                for index in range(1, count + 1):
                    child = self._collection_item(collection, index)
                    if not self._same_com_object(child.Page, shape.Page, strict=True) or not self._same_com_object(child.Layer, shape.Layer, strict=True):
                        raise CorelBridgeError('Contour descendants have foreign page/layer ownership.', ErrorCode.COREL_COM_ERROR)
                    self._offset_tree(child, nodes, depth + 1)
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError('Native contour/group/clip ownership is unreadable.', ErrorCode.UNSUPPORTED_IN_PROFILE) from exc
        return nodes

    def _offset_layer(self, layer):
        roots = self._vector_layer_members(layer)
        nodes = {}
        for index in range(1, len(roots) + 1):
            self._offset_tree(self._collection_item(layer.Shapes, index), nodes)
        return roots, nodes

    def _offset_source_signature(self, document, shape):
        try:
            effect_count = self._reference_count(shape.Effects)
            clip = shape.PowerClip
        except Exception as exc:
            raise CorelBridgeError('Contour source effect/clip metadata is unreadable.', ErrorCode.UNSUPPORTED_IN_PROFILE) from exc
        if effect_count != 0 or clip is not None:
            raise CorelBridgeError('Contour sources must be vectors without existing effects or clips.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        value = self._vector_source_signature(document, shape)
        fill = value['fill']; outline = value['outline']
        if fill['type_code'] not in (0, 1, 2) or fill['type_code'] == 1 and not complete_process_readback(fill['color']):
            raise CorelBridgeError('Contour sources currently support no fill, readable process fills or complete process gradients.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if outline['type_code'] not in (0, 1) or (outline['type_code'] == 1 and (not complete_process_readback(outline['color']) or
                type(outline['width_raw']) not in (int, float) or not math.isfinite(outline['width_raw']) or outline['width_raw'] <= 0)):
            raise CorelBridgeError('Contour sources require no outline or a readable ordinary process outline.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        value['gradient'] = self._gradient_state(document, shape) if fill['type_code'] == 2 else None
        if value['gradient'] is not None and not value['gradient']['complete']:
            raise CorelBridgeError('Contour source gradient metadata is incomplete.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        value['transparency'] = self._transparency_readback(shape)
        transparency = value['transparency']
        if not transparency['available'] or transparency['type_code'] not in (0, 1) or (transparency['type_code'] == 1 and
                any(transparency[k] is None for k in ('uniform_percent', 'applied_to_code', 'merge_mode_code'))):
            raise CorelBridgeError('Contour source transparency is unavailable or unsupported.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if any(not p['closed'] for p in value['curve']['paths']):
            raise CorelBridgeError('Contour offsets currently require complete closed vector paths.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        return value

    def _offset_capture(self, document, shape, state, existing_only=False):
        try:
            nodes = self._offset_tree(shape)
            roots = self._vector_layer_members(state['layer'])
            if roots.count(self._reference_identity(shape)) != 1:
                raise CorelBridgeError('Native contour receipt is not an independent expected-layer root.', ErrorCode.COREL_COM_ERROR)
            for key, node in nodes.items():
                if key in state['baseline_nodes'] or not self._same_com_object(node.Page, state['page'], strict=True) or not self._same_com_object(node.Layer, state['layer'], strict=True):
                    raise CorelBridgeError('Contour receipt contains original or foreign objects.', ErrorCode.COREL_COM_ERROR)
                if existing_only and key not in state['owned'] and node.Type not in (7, self.adapter.CDR_CONTOUR_GROUP_SHAPE):
                    raise CorelBridgeError('Contour separation introduced an ownership-uncertain new leaf.', ErrorCode.COREL_COM_ERROR)
                if node.Type == self.adapter.CDR_CURVE_SHAPE:
                    curve = self._reference_identity(node.Curve)
                    if curve in state['baseline_curves'] or curve in state['owned_curves'] and state['owned_curves'][curve] != key:
                        raise CorelBridgeError('Contour curves share original or other owned mutable data.', ErrorCode.COREL_COM_ERROR)
                    state['owned_curves'][curve] = key
            if len(set(state['owned']) | set(nodes) | state['baseline_nodes']) > MAX_OFFSET_SHAPES:
                raise CorelBridgeError('Original plus owned contour membership exceeds 1000 shapes.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            state['owned'].update(nodes)
            state['containers'].update(key for key, node in nodes.items() if node.Type in (7, self.adapter.CDR_CONTOUR_GROUP_SHAPE))
            return nodes
        except Exception:
            state['ownership_uncertain'] = True
            raise

    def _offset_effect_state(self, document, effect):
        if type(effect.Type) is not int or effect.Type != self.adapter.CDR_CONTOUR_EFFECT:
            raise CorelBridgeError('Native receipt is not a contour effect.', ErrorCode.COREL_COM_ERROR)
        native = effect.Contour
        if not self._same_com_object(native.Parent, effect, strict=True):
            raise CorelBridgeError('Native contour parent differs from its effect receipt.', ErrorCode.COREL_COM_ERROR)
        integers = ('Direction', 'Steps', 'ColorBlendType', 'ColorAcceleration', 'SpacingAcceleration', 'EndCapType', 'CornerType')
        result = {name: getattr(native, name) for name in integers}
        if any(type(v) is not int for v in result.values()):
            raise CorelBridgeError('Native contour parameter types are inconsistent.', ErrorCode.COREL_COM_ERROR)
        with self._in_inches(document, strict_restore=True):
            result.update(Offset=native.Offset, MiterLimit=native.MiterLimit)
        if any(type(result[k]) not in (int, float) or not math.isfinite(result[k]) for k in ('Offset', 'MiterLimit')):
            raise CorelBridgeError('Native contour distance/limit metadata is unavailable.', ErrorCode.COREL_COM_ERROR)
        for name in ('OutlineColor', 'FillColor', 'FillColorTo'):
            result[name] = self._color_readback(getattr(native, name))
        return result

    def _offset_discard(self, state, keep):
        layer = state['layer']
        for index in range(self._reference_count(layer.Shapes), 0, -1):
            if index > self._reference_count(layer.Shapes):
                continue
            root = self._collection_item(layer.Shapes, index)
            key = self._reference_identity(root)
            if key in state['baseline_nodes'] or key not in state['owned'] or key in keep:
                continue
            nodes = self._offset_tree(root)
            deleted_nodes = dict(nodes)
            if not set(nodes) <= set(state['owned']) or set(nodes) & state['baseline_nodes']:
                raise CorelBridgeError('Refusing to delete a contour tree containing foreign objects.', ErrorCode.COREL_COM_ERROR)
            for node in nodes.values():
                effects = node.Effects
                count = self._reference_count(effects)
                if count > 1:
                    raise CorelBridgeError('Contour cleanup found unaccounted native effects.', ErrorCode.COREL_COM_ERROR)
                if count:
                    effect = self._collection_item(effects, 1)
                    group = effect.Contour.ContourGroup
                    if effect.Type != self.adapter.CDR_CONTOUR_EFFECT or state['effect_groups'].get(self._reference_identity(effect)) != self._reference_identity(group):
                        raise CorelBridgeError('Contour cleanup cannot establish associated-effect ownership.', ErrorCode.COREL_COM_ERROR)
                    related = self._offset_tree(group)
                    if not set(related) <= set(state['owned']) or set(related) & state['baseline_nodes']:
                        raise CorelBridgeError('Refusing cleanup of an effect linked to foreign descendants.', ErrorCode.COREL_COM_ERROR)
                    deleted_nodes.update(related)
            self._note_mutation()
            self._layout_method(root, 'Delete')()
            for node in deleted_nodes.values():
                try:
                    foreign = not self._same_com_object(node.Page, state['page'], strict=True) or not self._same_com_object(node.Layer, layer, strict=True)
                except Exception:
                    continue  # A completed native Delete can invalidate its owned proxies.
                if foreign:
                    state['ownership_uncertain'] = True
                    raise CorelBridgeError('Deleted contour receipt remains live outside the expected scope.', ErrorCode.COREL_COM_ERROR)
            state['retired'].update(deleted_nodes)

    def _offset_check_owned_scope(self, state):
        for key, node in state['owned'].items():
            if key in state['retired']:
                continue
            try:
                valid = self._same_com_object(node.Page, state['page'], strict=True) and self._same_com_object(node.Layer, state['layer'], strict=True)
            except Exception as exc:
                state['ownership_uncertain'] = True
                raise CorelBridgeError('Remaining contour ownership cannot be located safely.', ErrorCode.COREL_COM_ERROR) from exc
            if not valid:
                state['ownership_uncertain'] = True
                raise CorelBridgeError('Owned contour objects moved outside the expected page/layer.', ErrorCode.COREL_COM_ERROR)

    def _offset_recover_affiliates(self, document, state):
        """Inspect owned controllers after a throw; never replay the failed call."""
        for key in state['controllers']:
            controller = state['owned'][key]
            count = self._reference_count(controller.Effects)
            if count == 0:
                continue
            if count != 1:
                raise CorelBridgeError('Failed contour controller has unaccounted effects.', ErrorCode.COREL_COM_ERROR)
            effect = self._collection_item(controller.Effects, 1)
            effect_key = self._reference_identity(effect)
            if effect_key in state['effect_groups']:
                continue
            if effect.Type != self.adapter.CDR_CONTOUR_EFFECT or not self._same_com_object(effect.Contour.Parent, effect, strict=True):
                raise CorelBridgeError('Failed contour effect ownership cannot be established.', ErrorCode.COREL_COM_ERROR)
            group = effect.Contour.ContourGroup
            if group.Type not in (7, self.adapter.CDR_CONTOUR_GROUP_SHAPE):
                raise CorelBridgeError('Failed contour affiliate is not a known group.', ErrorCode.COREL_COM_ERROR)
            self._offset_capture(document, group, state)
            state['effect_groups'][effect_key] = self._reference_identity(group)

    def _offset_flatten(self, state):
        layer = state['layer']
        while True:
            group = next((self._collection_item(layer.Shapes, i) for i in range(1, self._reference_count(layer.Shapes) + 1)
                          if self._reference_identity(self._collection_item(layer.Shapes, i)) in state['owned'] and self._collection_item(layer.Shapes, i).Type == 7), None)
            if group is None:
                return
            before = self._vector_layer_members(layer)
            group_key = self._reference_identity(group)
            children = [self._collection_item(group.Shapes, i) for i in range(1, self._reference_count(group.Shapes) + 1)]
            child_keys = {self._reference_identity(child) for child in children}
            if not child_keys <= set(state['owned']):
                state['ownership_uncertain'] = True
                raise CorelBridgeError('Contour group includes unowned children.', ErrorCode.COREL_COM_ERROR)
            self._note_mutation()
            self._layout_method(group, 'Ungroup')()
            after = self._vector_layer_members(layer)
            if set(after) != (set(before) - {group_key}) | child_keys:
                state['ownership_uncertain'] = True
                raise CorelBridgeError('Ungrouping did not retain exact owned child identities.', ErrorCode.COREL_COM_ERROR)
            state['retired'].add(group_key)

    @tracked_mutation
    def create_contour_offsets(self, object_reference, offset_inches, direction='outside', steps=1,
                               color=None, corner_type='round', miter_limit=0., result_name_prefix='AI_Contour'):
        if type(offset_inches) not in (int, float) or not math.isfinite(offset_inches) or not .0001 <= offset_inches <= 100:
            raise CorelBridgeError('offset_inches must be finite in [0.0001, 100].', ErrorCode.INVALID_ARGUMENT)
        if type(direction) is not str or direction not in ('inside', 'outside') or type(steps) is not int or not 1 <= steps <= 32:
            raise CorelBridgeError('Choose inside/outside and 1-32 integer contour steps.', ErrorCode.INVALID_ARGUMENT)
        if type(corner_type) is not str or corner_type not in self.adapter.CONTOUR_CORNER_CODES or type(miter_limit) not in (int, float) or not math.isfinite(miter_limit) or not 0 <= miter_limit <= 100:
            raise CorelBridgeError('Choose a supported native corner type and finite miter_limit in [0, 100].', ErrorCode.INVALID_ARGUMENT)
        validate_name(result_name_prefix, 110)
        if not result_name_prefix:
            raise CorelBridgeError('result_name_prefix must be nonempty.', ErrorCode.INVALID_ARGUMENT)
        requested, components = validate_process_color({'model': 'rgb', 'red': 0, 'green': 0, 'blue': 0} if color is None else color)
        document, sources = self._vector_inputs([object_reference], 1, 1)
        source = sources[0]; page = document.ActivePage; layer = source.Layer; saved_layer = page.ActiveLayer
        signature = self._offset_source_signature(document, source)
        self._layout_method(source, 'CreateContour')
        baseline, baseline_nodes = self._offset_layer(layer)
        if len(baseline_nodes) + steps + 3 > MAX_OFFSET_SHAPES:
            raise CorelBridgeError('Contour source scope leaves insufficient owned-output capacity.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        state = {'page': page, 'layer': layer, 'baseline_nodes': set(baseline_nodes),
                 'baseline_curves': {self._reference_identity(s.Curve if s.Type == self.adapter.CDR_CURVE_SHAPE else s.DisplayCurve)
                                     for s in baseline_nodes.values() if s.Type in self.adapter.VECTOR_PRIMITIVE_TYPES},
                 'owned': {}, 'owned_curves': {}, 'effect_groups': {}, 'controllers': set(), 'containers': set(), 'retired': set(), 'ownership_uncertain': False}
        create_color = self._layout_method(self.app, 'CreateRGBColor' if requested['model'] == 'rgb' else 'CreateCMYKColor')
        try:
            native_color = create_color(*components)
        except Exception as exc:
            raise CorelBridgeError('Could not prepare the contour process color.', ErrorCode.COREL_COM_ERROR) from exc
        expected_color = {k: v for k, v in requested.items() if k != 'model'}
        prepared = self._color_readback(native_color)
        if not prepared or prepared['model'] != requested['model'] or prepared['value'] != expected_color:
            raise CorelBridgeError('Native contour color differs from the requested components.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        opened = False
        try:
            self._note_mutation(); document.BeginCommandGroup('AI Contour Offsets'); opened = True
            layer.Activate()
            with self._in_inches(document, strict_restore=True), self._reference_point(document, strict_restore=True):
                self._note_mutation(); copy = source.Duplicate(0., 0.)
                self._offset_capture(document, copy, state)
                state['controllers'].add(self._reference_identity(copy))
                copied = self._offset_source_signature(document, copy)
                if any(copied[k] != signature[k] for k in ('type', 'transform', 'fill', 'outline', 'gradient', 'transparency')) or not paths_equivalent(signature['curve']['paths'], copied['curve']['paths']):
                    raise CorelBridgeError('Copied contour source differs in measured geometry/appearance.', ErrorCode.COREL_COM_ERROR)
                if source.Type == self.adapter.CDR_CURVE_SHAPE and (not paths_match(signature['curve']['paths'], copied['curve']['paths']) or signature['curve']['node_types'] != copied['curve']['node_types']):
                    raise CorelBridgeError('Copied contour source changed full curve topology or node types.', ErrorCode.COREL_COM_ERROR)
                if copy.Type != self.adapter.CDR_CURVE_SHAPE:
                    self._note_mutation(); self._layout_method(copy, 'ConvertToCurves')()
                    if copy.Type != self.adapter.CDR_CURVE_SHAPE:
                        raise CorelBridgeError('Copied contour source did not become an editable curve.', ErrorCode.COREL_COM_ERROR)
                    self._offset_capture(document, copy, state)
                    converted = self._offset_source_signature(document, copy)
                    if not paths_equivalent(signature['curve']['paths'], converted['curve']['paths']) or any(converted[k] != copied[k] for k in ('fill', 'outline', 'gradient', 'transparency')):
                        raise CorelBridgeError('Converted contour source changed measured geometry/appearance.', ErrorCode.COREL_COM_ERROR)
                controller_geometry = self._vector_snapshot(document, copy)[0]
                copy_key = self._reference_identity(copy)
                self._note_mutation()
                effect = self._layout_method(copy, 'CreateContour')(self.adapter.CONTOUR_DIRECTION_CODES[direction], offset_inches, steps,
                    self.adapter.CDR_DIRECT_FOUNTAIN_BLEND, native_color, native_color, native_color, 0, 0,
                    self.adapter.CDR_CONTOUR_BUTT_CAP, self.adapter.CONTOUR_CORNER_CODES[corner_type], miter_limit)
                if self._reference_count(copy.Effects) != 1 or not self._same_com_object(self._collection_item(copy.Effects, 1), effect, strict=True):
                    raise CorelBridgeError('Contour receipt is not the copied source effect.', ErrorCode.COREL_COM_ERROR)
                native = effect.Contour
                group = native.ContourGroup
                if group.Type != self.adapter.CDR_CONTOUR_GROUP_SHAPE:
                    raise CorelBridgeError('Native contour receipt does not identify a contour group.', ErrorCode.COREL_COM_ERROR)
                self._offset_capture(document, group, state)
                state['effect_groups'][self._reference_identity(effect)] = self._reference_identity(group)
                actual = self._offset_effect_state(document, effect)
                expected = {'Direction': self.adapter.CONTOUR_DIRECTION_CODES[direction], 'Steps': steps,
                            'ColorBlendType': self.adapter.CDR_DIRECT_FOUNTAIN_BLEND, 'ColorAcceleration': 0, 'SpacingAcceleration': 0,
                            'EndCapType': self.adapter.CDR_CONTOUR_BUTT_CAP, 'CornerType': self.adapter.CONTOUR_CORNER_CODES[corner_type]}
                if any(actual[k] != v for k, v in expected.items()) or not math.isclose(actual['Offset'], offset_inches, rel_tol=1e-8, abs_tol=1e-8) or not math.isclose(actual['MiterLimit'], miter_limit, rel_tol=1e-8, abs_tol=1e-8):
                    raise CorelBridgeError('Native contour controls differ from the requested values.', ErrorCode.COREL_COM_ERROR)
                if any(not actual[k] or actual[k]['model'] != requested['model'] or actual[k]['value'] != expected_color for k in ('OutlineColor', 'FillColor', 'FillColorTo')):
                    raise CorelBridgeError('Native contour colors differ from the requested components.', ErrorCode.COREL_COM_ERROR)
                controller_now = self._vector_snapshot(document, copy)[0]
                if not paths_match(controller_geometry['paths'], controller_now['paths']) or controller_geometry['node_types'] != controller_now['node_types'] or copied['fill'] != self._fill_readback(copy) or copied['outline'] != self._outline_readback(copy) or copied['transparency'] != self._transparency_readback(copy) or (copied['gradient'] is not None and copied['gradient'] != self._gradient_state(document, copy)):
                    raise CorelBridgeError('Native contour creation changed the copied controller geometry/appearance.', ErrorCode.COREL_COM_ERROR)
                measured = {key: self._vector_snapshot(document, node)[0] for key, node in state['owned'].items() if node.Type == self.adapter.CDR_CURVE_SHAPE and key != copy_key}
                self._note_mutation()
                separated = self._layout_method(effect, 'Separate')()
                count = self._reference_count(separated)
                if not 1 <= count <= MAX_OFFSET_OUTPUTS + 1:
                    raise CorelBridgeError('Contour separation returned an invalid bounded receipt.', ErrorCode.COREL_COM_ERROR)
                for index in range(1, count + 1):
                    self._offset_capture(document, self._collection_item(separated, index), state, existing_only=True)
                self._offset_flatten(state)
                roots, nodes = self._offset_layer(layer)
                if set(nodes) - state['baseline_nodes'] - set(state['owned']):
                    state['ownership_uncertain'] = True
                    raise CorelBridgeError('Contour separation introduced objects without verified ownership.', ErrorCode.COREL_COM_ERROR)
                for key, before in measured.items():
                    if key not in nodes:
                        state['ownership_uncertain'] = True
                        raise CorelBridgeError('Generated contour leaf is missing from its owned scope.', ErrorCode.COREL_COM_ERROR)
                    if self._vector_snapshot(document, nodes[key])[0] != before:
                        raise CorelBridgeError('Contour separation/ungrouping changed generated curve identities or geometry.', ErrorCode.COREL_COM_ERROR)
                if copy_key not in nodes or self._vector_snapshot(document, copy)[0] != controller_geometry:
                    if copy_key not in nodes:
                        state['ownership_uncertain'] = True
                    raise CorelBridgeError('Separated contour controller differs from its pre-effect curve geometry.', ErrorCode.COREL_COM_ERROR)
                for key in state['containers'] - set(nodes) - state['retired']:
                    old_container = state['owned'][key]
                    try:
                        foreign = not self._same_com_object(old_container.Page, page, strict=True) or not self._same_com_object(old_container.Layer, layer, strict=True)
                    except Exception:
                        foreign = False  # Completed separation retained every owned leaf; obsolete container proxies can be invalid.
                    if foreign:
                        state['ownership_uncertain'] = True
                        raise CorelBridgeError('Separated contour container remains live in a foreign scope.', ErrorCode.COREL_COM_ERROR)
                    state['retired'].add(key)
                outputs = [nodes[key] for key in roots if key in state['owned'] and key != copy_key]
                if len(outputs) > MAX_OFFSET_OUTPUTS or not outputs and direction != 'inside':
                    raise CorelBridgeError('Contour produced no outside geometry or too many independent curves.', ErrorCode.COREL_COM_ERROR)
                geometry = [self._vector_snapshot(document, s)[0] for s in outputs]
                if sum(s['node_count'] for s in geometry) > MAX_OFFSET_NODES or any(not p['closed'] for s in geometry for p in s['paths']):
                    raise CorelBridgeError('Generated contours exceed 16384 nodes or contain open paths.', ErrorCode.UNSUPPORTED_IN_PROFILE)
                if outputs:
                    bounds = [s['bounds_inches'] for s in geometry]
                    left = min(b['x'] for b in bounds); bottom = min(b['y'] for b in bounds)
                    right = max(b['x'] + b['width'] for b in bounds); top = max(b['y'] + b['height'] for b in bounds)
                    src = signature['curve']['bounds_inches']; tol = max(1e-7, min(0.0001, offset_inches * .001))
                    if direction == 'inside':
                        valid = left >= src['x'] + offset_inches - tol and bottom >= src['y'] + offset_inches - tol and right <= src['x'] + src['width'] - offset_inches + tol and top <= src['y'] + src['height'] - offset_inches + tol
                    elif corner_type == 'round':
                        extent = steps * offset_inches
                        valid = all(math.isclose(a, b, abs_tol=tol, rel_tol=0.) for a, b in zip((left, bottom, right, top),
                            (src['x'] - extent, src['y'] - extent, src['x'] + src['width'] + extent, src['y'] + src['height'] + extent)))
                    else:
                        valid = left <= src['x'] and bottom <= src['y'] and right >= src['x'] + src['width'] and top >= src['y'] + src['height'] and (left < src['x'] or right > src['x'] + src['width'] or bottom < src['y'] or top > src['y'] + src['height'])
                    if not valid:
                        raise CorelBridgeError('Generated contour bounds do not reconcile with the requested direction/distance envelope.', ErrorCode.COREL_COM_ERROR)
                for index, output in enumerate(outputs, 1):
                    if output.Type != self.adapter.CDR_CURVE_SHAPE or self._reference_count(output.Effects) != 0 or output.PowerClip is not None:
                        raise CorelBridgeError('Separated contours are not ordinary effect-free editable curves.', ErrorCode.COREL_COM_ERROR)
                    self._note_mutation(); output.Name = f'{result_name_prefix}_{index:03d}'
                    self._note_mutation(); self._layout_method(output.Fill, 'ApplyUniformFill')(native_color)
                    self._note_mutation(); self._layout_method(output.Outline, 'SetNoOutline')()
                    self._note_mutation(); self._layout_method(output.Transparency, 'ApplyNoTransparency')()
                    fill = self._fill_readback(output); outline = self._outline_readback(output); transparency = self._transparency_readback(output)
                    if output.Name != f'{result_name_prefix}_{index:03d}' or fill['type_code'] != 1 or not fill['color'] or fill['color']['model'] != requested['model'] or fill['color']['value'] != expected_color or outline['type_code'] != 0 or transparency['type_code'] != 0 or self._vector_snapshot(document, output)[0] != geometry[index - 1]:
                        raise CorelBridgeError('Final contour color/name or geometry readback differs from the result contract.', ErrorCode.COREL_COM_ERROR)
                keep = {self._reference_identity(s) for s in outputs}
                self._offset_discard(state, keep)
                self._offset_check_owned_scope(state)
                roots, nodes = self._offset_layer(layer)
                if set(roots) != set(baseline) | keep or [k for k in roots if k in baseline] != baseline or set(nodes) != state['baseline_nodes'] | keep or self._offset_source_signature(document, source) != signature:
                    if set(nodes) != state['baseline_nodes'] | keep:
                        state['ownership_uncertain'] = True
                    raise CorelBridgeError('Contour operation changed original membership/order or measured source state.', ErrorCode.COREL_COM_ERROR)
                objects = []
                for output in outputs:
                    reference = self._reference_for_shape(document, output)
                    if reference is None:
                        raise CorelBridgeError('Contour output lacks a signed editing reference.', ErrorCode.COREL_COM_ERROR)
                    objects.append(self.get_curve_geometry(object_reference=reference))
            document.EndCommandGroup(); opened = False; saved_layer.Activate()
            return {'created': bool(outputs), 'empty_result': not outputs, 'created_count': len(outputs), 'objects': objects,
                    'direction': direction, 'offset_inches': float(offset_inches), 'requested_steps': steps,
                    'native_parameters': actual, 'source_fingerprint': signature['curve']['fingerprint'],
                    'source_preservation': {'verified': True, 'scope': 'root_membership_relative_order_complete_measured_source_geometry_supported_appearance'},
                    'verification_status': 'implemented_unverified',
                    'warnings': ['Native parameters and complete measured curves are reconciled; exact arbitrary-curve offset distance, winding, collapsed steps, miter-limit semantics and cutting/print readiness require consolidated/manual verification.']}
        except Exception as exc:
            rollback = {'attempted': True, 'verified': False}
            try:
                try:
                    self._offset_check_owned_scope(state)
                except Exception as scope_error:
                    rollback['scope_error_type'] = type(scope_error).__name__
                try:
                    self._offset_recover_affiliates(document, state)
                except Exception as affiliate_error:
                    rollback['affiliates_error_type'] = type(affiliate_error).__name__
                self._offset_discard(state, set())
                if opened:
                    document.EndCommandGroup(); opened = False
                saved_layer.Activate()
                roots, nodes = self._offset_layer(layer)
                if set(nodes) != state['baseline_nodes']:
                    state['ownership_uncertain'] = True
                rollback['verified'] = roots == baseline and set(nodes) == state['baseline_nodes'] and self._offset_source_signature(document, source) == signature and not state['ownership_uncertain']
            except Exception as cleanup:
                rollback['error_type'] = type(cleanup).__name__
            raise CorelBridgeError('Contour offsets could not complete safely. ' + ('Owned outputs were discarded and measured source state verified.' if rollback['verified'] else 'Inspect exact source/output state before recovery.'),
                                   exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
                                   {'rollback': rollback, 'ownership_uncertain': state['ownership_uncertain']}) from exc
