"""Native bitmap metadata and placed affine resolution without pixel mutation."""
from __future__ import annotations

import math
from contextlib import contextmanager

from .bitmap_geometry import affine_pixel_resolution, corners_bounds
from .errors import CorelBridgeError, ErrorCode
from .vector_geometry import fingerprint

MAX_BITMAP_PIXELS = 500_000_000


class BitmapBridgeMixin:
    @contextmanager
    def _bitmap_inspection_context(self, document):
        try:
            units, reference = document.Unit, document.ReferencePoint
        except Exception as exc:
            raise CorelBridgeError('Bitmap inspection context metadata is unavailable.', ErrorCode.COREL_COM_ERROR) from exc
        if type(units) is not int or type(reference) is not int:
            raise CorelBridgeError('Bitmap inspection requires readable unit/reference metadata.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        try:
            with self._in_inches(document, strict_restore=True), self._reference_point(document, strict_restore=True):
                if document.Unit != self.CDR_INCH or document.ReferencePoint != self.CDR_BOTTOM_LEFT:
                    raise CorelBridgeError('Native bitmap inspection context did not reconcile.', ErrorCode.COREL_COM_ERROR)
                yield
        finally:
            try:
                restored_units, restored_reference = document.Unit, document.ReferencePoint
            except Exception as exc:
                raise CorelBridgeError('Bitmap inspection context restoration is unreadable.', ErrorCode.COREL_COM_ERROR) from exc
            if type(restored_units) is not int or type(restored_reference) is not int or restored_units != units or restored_reference != reference:
                raise CorelBridgeError('Bitmap inspection could not verify unit/reference restoration.', ErrorCode.COREL_COM_ERROR)

    def _bitmap_box(self, bitmap):
        """Read exactly one four-line closed uncropped native parallelogram."""
        curve = bitmap.BoundingBoxPath
        if self._reference_count(curve.SubPaths) != 1 or self._reference_count(curve.Nodes) != 4 or self._reference_count(curve.Segments) != 4:
            raise ValueError('uncropped_box_not_four_lines')
        path = self._collection_item(curve.SubPaths, 1)
        if path.Closed is not True or self._reference_count(path.Nodes) != 4 or self._reference_count(path.Segments) != 4:
            raise ValueError('uncropped_box_topology')
        nodes = [self._collection_item(path.Nodes, i) for i in range(1, 5)]
        segments = [self._collection_item(path.Segments, i) for i in range(1, 5)]
        node_keys = [self._reference_identity(node) for node in nodes]
        segment_keys = [self._reference_identity(segment) for segment in segments]
        aggregate_nodes = {self._reference_identity(self._collection_item(curve.Nodes, i)) for i in range(1, 5)}
        aggregate_segments = {self._reference_identity(self._collection_item(curve.Segments, i)) for i in range(1, 5)}
        if len(set(node_keys)) != 4 or len(set(segment_keys)) != 4 or aggregate_nodes != set(node_keys) or aggregate_segments != set(segment_keys):
            raise ValueError('uncropped_box_aliases')
        result = []
        for i, node in enumerate(nodes):
            segment = segments[i]
            if (not self._same_com_object(node.SubPath, path, strict=True) or type(segment.Type) is not int or segment.Type != 0 or
                not self._same_com_object(segment.SubPath, path, strict=True) or
                not self._same_com_object(segment.StartNode, node, strict=True) or
                not self._same_com_object(segment.EndNode, nodes[(i + 1) % 4], strict=True)):
                raise ValueError('uncropped_box_connectivity')
            position = {'x': node.PositionX, 'y': node.PositionY}
            if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1_000_000 for v in position.values()):
                raise ValueError('uncropped_box_coordinates')
            result.append({key: float(value) for key, value in position.items()})
        return {'corners_inches': result, 'bounds_inches': corners_bounds(result)}

    def _bitmap_scope_effects(self, document, shape, reference):
        owners = [shape]
        if reference is None:
            return ['unavailable_signed_object_scope']
        if reference['ancestor_identities']:
            _, _, _, layer = self._reference_scope(document, reference['page_identity'], reference['layer_identity'], self._reference_budget())
            collection = layer.Shapes
            for expected, index in zip(reference['ancestor_identities'], reference['shape_path'][:-1]):
                parent = self._collection_item(collection, index)
                if parent.Type != self.adapter.CDR_GROUP_SHAPE or self._reference_identity(parent) != expected:
                    return ['changed_ancestor_scope']
                owners.append(parent); collection = parent.Shapes
        reasons = []
        for owner in owners:
            try:
                if self._reference_count(owner.Effects) != 0:
                    reasons.append('bitmap_or_ancestor_effects')
                if owner.PowerClip is not None:
                    reasons.append('bitmap_or_ancestor_clipping')
            except Exception:
                reasons.append('unavailable_bitmap_or_ancestor_effect_scope')
        return sorted(set(reasons))

    def get_bitmap_properties(self, minimum_dpi=150., object_name='', shape_index=0, object_reference=None):
        if type(minimum_dpi) not in (int, float) or not math.isfinite(minimum_dpi) or not 1 <= minimum_dpi <= 2400:
            raise CorelBridgeError('minimum_dpi must be finite in [1, 2400].', ErrorCode.INVALID_ARGUMENT)
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        if type(shape.Type) is not int or shape.Type != 5:
            raise CorelBridgeError('Bitmap properties require an exact native bitmap shape.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        unavailable = []

        def read(owner, name, kind, low=None, high=None):
            try:
                value = getattr(owner, name)
                if type(value) is kind and (low is None or low <= value <= high):
                    return value
            except Exception:
                pass
            unavailable.append(name)
            return None

        transform = None; box = None; reasons = []; consistency = 'not_checked'
        with self._bitmap_inspection_context(document):
            try:
                bitmap = shape.Bitmap
            except Exception:
                bitmap = None
            width = read(bitmap, 'SizeWidth', int, 1, 1_000_000)
            height = read(bitmap, 'SizeHeight', int, 1, 1_000_000)
            data = {'available': bitmap is not None, 'size_pixels': {'width': width, 'height': height},
                'native_resolution': {'x': read(bitmap, 'ResolutionX', int, 1, 1_000_000), 'y': read(bitmap, 'ResolutionY', int, 1, 1_000_000)},
                'mode_code': read(bitmap, 'Mode', int, 0, 1000), 'externally_linked': read(bitmap, 'ExternallyLinked', bool),
                'embedded': read(bitmap, 'Embedded', bool), 'can_be_cropped': read(bitmap, 'Cropped', bool),
                'crop_envelope_modified': read(bitmap, 'CropEnvelopeModified', bool)}
            if width is None or height is None:
                reasons.append('unavailable_pixel_dimensions')
            elif width * height > MAX_BITMAP_PIXELS:
                reasons.append('pixel_dimensions_exceed_500_million_budget')
            try:
                transform = self._layout_snapshot(document, shape)
            except Exception:
                reasons.append('unavailable_native_transform')
            try:
                box = self._bitmap_box(bitmap)
            except Exception:
                reasons.append('unavailable_complete_uncropped_box')
            try:
                effect_scope = self._bitmap_scope_effects(document, shape, identity.get('object_reference'))
                reasons.extend(effect_scope)
            except Exception:
                effect_scope = None
                reasons.append('unavailable_bitmap_or_ancestor_effect_scope')
            if data['crop_envelope_modified'] is None:
                reasons.append('unavailable_crop_envelope_state')
            if box is not None and transform is not None:
                actual, uncropped = transform['bounds_inches'], box['bounds_inches']
                tolerance = max(1e-7, max(uncropped['width'], uncropped['height']) * 1e-6)
                if data['crop_envelope_modified'] is False:
                    if any(not math.isclose(actual[key], uncropped[key], rel_tol=0., abs_tol=tolerance) for key in actual):
                        reasons.append('uncropped_box_disagrees_with_placed_bounds')
                elif data['crop_envelope_modified'] is True:
                    if (actual['width'] <= 0 or actual['height'] <= 0 or actual['x'] < uncropped['x'] - tolerance or actual['y'] < uncropped['y'] - tolerance or
                        actual['x'] + actual['width'] > uncropped['x'] + uncropped['width'] + tolerance or
                        actual['y'] + actual['height'] > uncropped['y'] + uncropped['height'] + tolerance):
                        reasons.append('crop_bounds_outside_uncropped_pixel_grid')
            if width is not None and height is not None and transform is not None and box is not None and data['crop_envelope_modified'] is not None and effect_scope is not None:
                try:
                    counts = (bitmap.SizeWidth, bitmap.SizeHeight, bitmap.CropEnvelopeModified)
                    counts_before = (width, height, data['crop_envelope_modified'])
                    same_counts = all(type(a) is type(b) and a == b for a, b in zip(counts, counts_before))
                    second_transform = self._layout_snapshot(document, shape)
                    second_box = self._bitmap_box(bitmap)
                    second_scope = self._bitmap_scope_effects(document, shape, identity.get('object_reference'))
                    reference = identity.get('object_reference')
                    if reference is not None:
                        resolved, _ = self._resolve_object_reference(document, reference)
                        if not self._same_com_object(resolved, shape, strict=True):
                            raise ValueError('Changed native object identity')
                    if not same_counts or second_transform != transform or second_box != box or second_scope != effect_scope:
                        consistency = 'changed'; reasons.append('native_bitmap_state_changed_during_inspection')
                    else:
                        consistency = 'two_reads_reconciled'
                except Exception:
                    consistency = 'not_checked'; reasons.append('native_bitmap_state_consistency_unavailable')
        if not self._same_com_object(self._target_document(), document, strict=True):
            raise CorelBridgeError('Bitmap inspection target changed during native readback.', ErrorCode.NO_TARGET_DOCUMENT)
        data['unavailable_properties'] = unavailable
        effective = {'status': 'indeterminate', 'axis_dpi': None, 'minimum_direction_dpi': None,
            'pixel_axis_extents_inches': None, 'minimum_required_dpi': float(minimum_dpi),
            'resolution_check': 'not_checked', 'basis': 'uncropped_native_box_pixel_dimensions_and_affine_axes', 'reasons': []}
        if not reasons:
            try:
                result = affine_pixel_resolution(box['corners_inches'], width, height, transform['matrix'])
                effective.update(result, status='calculated', resolution_check='pass' if result['minimum_direction_dpi'] >= minimum_dpi else 'below_requested')
            except ValueError as exc:
                reasons.append(str(exc))
        effective['reasons'] = sorted(set(reasons))
        result = {'object': identity, 'bitmap': data, 'transform': transform, 'uncropped_box': box,
            'inspection_consistency': {'status': consistency, 'scope': 'pixel_counts_crop_state_bounds_matrix_uncropped_box_and_effect_scope'},
            'effective_resolution': effective, 'verification_status': 'implemented_unverified',
            'warnings': ['Native pixel counts and DPI metadata do not prove source detail, pixel fidelity, color/profile correctness or print readiness.',
                'Calculated DPI uses uncropped placed affine pixel axes; cropping does not create additional pixel detail. Native path/matrix semantics require consolidated verification.']}
        result['fingerprint'] = fingerprint({'bridge_session_id': self._bridge_session_id,
            'document_session_id': self._document_session_id(document), 'shape_identity': self._reference_identity(shape), 'inspection': result})
        return result
