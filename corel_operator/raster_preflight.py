"""Bounded whole-document native bitmap and local linked-file preflight."""
from __future__ import annotations

import math
import os
import stat
from pathlib import Path

from .errors import CorelBridgeError, ErrorCode
from .vector_geometry import fingerprint

MAX_PREFLIGHT_SHAPES = 4096
MAX_PREFLIGHT_DEPTH = 32
# Existing X7 cdrShapeType evidence distinguishes ordinary leaves from opaque
# containers; unknown native types cannot prove absence of nested raster content.
PREFLIGHT_LEAF_TYPES = {1, 2, 3, 4, 5, 6, 9, 14, 19, 20, 26}
PREFLIGHT_EFFECT_GROUP_TYPES = {10, 11, 13, 15, 16, 18, 22}


def local_link_presence(filename, document_filename):
    """Observe local regular-file presence; never resolve/update a native link."""
    result = {'status': 'indeterminate', 'resolved_path': None, 'file_bytes': None,
              'file_state_fingerprint': None, 'reason': None}
    if type(filename) is not str or not filename or len(filename) > 32767 or any(ord(c) < 32 for c in filename):
        result['reason'] = 'unavailable_or_invalid_link_filename'; return result
    def local(path):
        return not str(path).startswith(('\\\\', '//')) and not (os.name == 'nt' and (path.is_reserved() or ':' in path.name))
    path = Path(filename)
    relative = not path.is_absolute()
    if not local(path):
        result['reason'] = 'remote_or_device_link_not_checked'; return result
    if not path.is_absolute():
        if type(document_filename) is not str or not document_filename or len(document_filename) > 32767 or any(ord(c) < 32 for c in document_filename):
            result['reason'] = 'relative_link_without_saved_document_base'; return result
        base = Path(document_filename)
        if not base.is_absolute() or not local(base):
            result['reason'] = 'relative_link_without_local_document_base'; return result
        path = base.parent / path
    try:
        path = path.resolve(strict=False)
        if not local(path):
            result['reason'] = 'remote_or_device_link_not_checked'; return result
        result['resolved_path'] = str(path)
        metadata = path.stat()
        result['file_bytes'] = metadata.st_size
        result['file_state_fingerprint'] = fingerprint({'path': str(path), 'device': metadata.st_dev,
            'inode': metadata.st_ino, 'size': metadata.st_size, 'mtime_ns': metadata.st_mtime_ns, 'ctime_ns': metadata.st_ctime_ns})
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
            result.update(status='failed', reason='linked_source_not_nonempty_regular_file')
        else:
            result.update(status='passed', reason=None)
    except FileNotFoundError:
        result.update(status='failed', reason='linked_source_missing')
    except Exception:
        result['reason'] = 'local_link_presence_unreadable'
    if relative:
        result.update(status='indeterminate', reason='relative_link_base_requires_native_verification')
    return result


class RasterPreflightMixin:
    def _raster_context(self, document):
        try:
            unit, reference, dirty = document.Unit, document.ReferencePoint, document.Dirty
            if type(unit) is not int or type(reference) is not int or not (type(dirty) is bool or type(dirty) is int and dirty in (-1, 0)):
                raise ValueError('Invalid native context')
            selection = document.SelectionRange; count = self._reference_count(selection)
            if count > MAX_PREFLIGHT_SHAPES: raise ValueError('Selection budget')
            identities = [self._reference_identity(self._collection_item(selection, index)) for index in range(1, count+1)]
            if len(set(identities)) != count: raise ValueError('Ambiguous selection')
            page = document.ActivePage
            return {'unit_code': unit, 'reference_point_code': reference, 'dirty': bool(dirty),
                'selection_identities': identities, 'active_page_identity': self._reference_identity(page),
                'active_layer_identity': self._reference_identity(page.ActiveLayer)}
        except Exception as exc:
            raise CorelBridgeError('Raster preflight requires bounded readable native context and selection.', ErrorCode.UNSUPPORTED_IN_PROFILE) from exc

    def _raster_link_snapshot(self, document, shape, bitmap_metadata):
        result = {'externally_linked': bitmap_metadata['externally_linked'], 'opi_linked': None,
            'eps_placeholder': None, 'native_filename': None, 'bitmap_identity': None,
            'presence': {'status': 'indeterminate', 'resolved_path': None, 'file_bytes': None,
                         'file_state_fingerprint': None, 'reason': 'native_link_metadata_unavailable'}}
        try:
            bitmap = shape.Bitmap
            try: result['bitmap_identity'] = self._reference_identity(bitmap)
            except Exception: pass
            for name, key in [('OPILinked', 'opi_linked'), ('IsEPS', 'eps_placeholder')]:
                try:
                    value = getattr(bitmap, name)
                    if type(value) is bool: result[key] = value
                except Exception: pass
            if result['externally_linked'] is False and result['opi_linked'] is False:
                result['presence'].update(status='not_applicable', reason=None)
            elif result['externally_linked'] is True or result['opi_linked'] is True:
                name = bitmap.LinkFileName
                if type(name) is str and len(name) <= 32767 and not any(ord(c) < 32 for c in name): result['native_filename'] = name
                result['presence'] = local_link_presence(name, getattr(document, 'FullFileName', None))
        except Exception:
            pass
        if result['opi_linked'] is not False and result['presence']['status'] in ('passed', 'not_applicable'):
            result['presence'].update(status='indeterminate', reason='opi_source_mapping_requires_native_verification' if result['opi_linked'] is True else 'native_opi_link_state_unavailable')
        return result

    def _raster_scope_reasons(self, document, owners, master, clipped):
        reasons = ['master_bitmap_coordinate_mapping_not_verified'] if master else []
        if clipped: reasons.append('bitmap_inside_powerclip_coordinate_scope')
        for ancestor in owners[:-1]:
            if ancestor.Type in PREFLIGHT_EFFECT_GROUP_TYPES:
                reasons.append('special_native_effect_group_rendering_not_verified')
            try: self._layout_snapshot(document, ancestor)
            except Exception: reasons.append('ancestor_transform_unreadable')
        for owner in owners:
            try:
                if self._reference_count(owner.Effects): reasons.append('bitmap_or_ancestor_effects')
                if owner.PowerClip is not None: reasons.append('bitmap_or_ancestor_clipping')
            except Exception: reasons.append('unavailable_bitmap_or_ancestor_effect_scope')
        return sorted(set(reasons))

    def _raster_scan(self, document, structure, pages, layers, minimum_dpi, include_nonprinting, max_shapes):
        seen = set(); nodes = []; rasters = []; issues = []; issue_keys = set(); excluded = []; scanned_layers = 0; accessed = 0

        def issue(code, location=None):
            key = code, fingerprint(location) if location is not None else None
            if len(issues) < MAX_PREFLIGHT_SHAPES+1 and key not in issue_keys:
                issue_keys.add(key)
                issues.append({'code': code, 'location': location})

        def visit(shape, page, layer, location, owners=(), clipped=False):
            nonlocal accessed
            if accessed >= max_shapes:
                issue('shape_budget_exhausted'); return
            accessed += 1
            if len(location['path']) > MAX_PREFLIGHT_DEPTH+1:
                issue('maximum_nesting_depth_exceeded', location); return
            try:
                key = self._reference_identity(shape)
                if key in seen:
                    issue('aliased_or_cyclic_shape_membership', location); return
                seen.add(key); location = {**location, 'shape_identity': key}
                if not self._same_com_object(shape.Page, page, strict=True) or not self._same_com_object(shape.Layer, layer, strict=True):
                    issue('foreign_shape_ownership', location); return
                if owners:
                    parent = shape.ParentGroup if location['path'][-1]['kind'] == 'group' else shape.PowerClipParent
                    if not self._same_com_object(parent, owners[-1], strict=True):
                        issue('inconsistent_parent_ownership', location); return
                code, name, sid = shape.Type, shape.Name, shape.StaticID
                if type(code) is not int or not 0 <= code <= 1000 or type(name) is not str or len(name) > 512 or type(sid) is not int or not 0 <= sid <= 2147483647:
                    issue('unavailable_shape_identity_metadata', location); return
                location = {**location, 'object_name': name, 'static_id': sid}
                node = {'location': location, 'shape_type_code': code, 'group_children': None, 'clip_children': None,
                    'ancestor_transform': None, 'effects_count': None, 'bitmap_fingerprint': None}
                nodes.append(node)
                try: node['effects_count'] = self._reference_count(shape.Effects)
                except Exception: pass
                try: groups, clip = self._clip_children(shape)
                except Exception:
                    groups, clip = None, None; issue('native_child_membership_unreadable', location)
                if code in PREFLIGHT_EFFECT_GROUP_TYPES:
                    issue('special_native_container_rendering_not_checked', location)
                    try: groups = shape.Shapes
                    except Exception: issue('native_child_membership_unreadable', location)
                elif code not in PREFLIGHT_LEAF_TYPES and code != self.adapter.CDR_GROUP_SHAPE:
                    issue('opaque_or_unknown_native_raster_container', location)
                if code == self.adapter.CDR_GROUP_SHAPE or code in PREFLIGHT_EFFECT_GROUP_TYPES or clip is not None:
                    try: node['ancestor_transform'] = self._layout_snapshot(document, shape)
                    except Exception: issue('ancestor_transform_unreadable', location)
                if code == 5:
                    identity = self._shape_identity(shape)
                    identity.update(shape_index=None, object_reference=None)
                    evidence = self._read_bitmap_properties(document, shape, identity, minimum_dpi,
                        lambda: self._raster_scope_reasons(document, (*owners, shape), location['scope'] == 'master', clipped))
                    link = self._raster_link_snapshot(document, shape, evidence['bitmap'])
                    effective = evidence['effective_resolution']
                    resolution = {'pass': 'passed', 'below_requested': 'failed', 'not_checked': 'indeterminate'}[effective['resolution_check']]
                    reasons = list(effective['reasons'])
                    if link['eps_placeholder'] is not False:
                        resolution = 'indeterminate'
                        reasons.append('eps_placeholder_resolution_not_final_raster' if link['eps_placeholder'] is True else 'eps_placeholder_state_unavailable')
                    linked = link['presence']['status']
                    status = 'failed' if 'failed' in (resolution, linked) else 'indeterminate' if 'indeterminate' in (resolution, linked) else 'passed'
                    if link['presence']['reason']: reasons.append(link['presence']['reason'])
                    row = {'location': location, 'bitmap': evidence['bitmap'], 'transform': evidence['transform'],
                        'uncropped_box': evidence['uncropped_box'], 'effective_resolution': effective,
                        'bitmap_consistency': evidence['inspection_consistency'], 'link': link,
                        'checks': {'effective_resolution': resolution, 'linked_source_presence': linked},
                        'observed_status': status, 'status': status, 'reasons': sorted(set(reasons))}
                    rasters.append(row); node['bitmap_fingerprint'] = fingerprint(row)
                for collection, kind, field in ((groups, 'group', 'group_children'), (None if clip is None else clip.Shapes, 'powerclip', 'clip_children')):
                    if collection is None: node[field] = []; continue
                    try:
                        count = self._reference_count(collection); identities = []
                        node[field] = identities
                        if count > max_shapes-accessed: issue('shape_budget_exhausted')
                        for index in range(1, min(count, max_shapes-accessed)+1):
                            child = self._collection_item(collection, index); identities.append(self._reference_identity(child))
                            visit(child, page, layer, {**location, 'shape_identity': None, 'static_id': None, 'object_name': None,
                                'path': location['path'] + [{'kind': kind, 'index': index}]}, (*owners, shape), clipped or kind == 'powerclip')
                            if accessed >= max_shapes: break
                        if self._reference_count(collection) != count: issue('native_child_membership_changed', location)
                    except Exception as exc:
                        if isinstance(exc, CorelBridgeError) and exc.code == ErrorCode.NO_TARGET_DOCUMENT: raise
                        issue('native_child_membership_unreadable', location)
            except CorelBridgeError as exc:
                if exc.code == ErrorCode.NO_TARGET_DOCUMENT: raise
                issue('native_shape_inspection_unavailable', location)
            except Exception:
                issue('native_shape_inspection_unavailable', location)

        with self._bitmap_inspection_context(document):
            scopes = [(row, pages[row['page_identity']], layer, 'page', [row['page_index']])
                for row in structure['pages'] for layer in row['layers']]
            for layer in structure['master_layers']:
                applied = [page['page_index'] for page in structure['pages'] if layer['layer_identity'] in page['all_layer_identities']]
                scopes.append((None, document.MasterPage, layer, 'master', applied))
            for page_row, page, layer_row, scope, applied in scopes:
                if not include_nonprinting and (not layer_row['printable'] or not applied):
                    excluded.append({'layer_identity': layer_row['layer_identity'], 'reason': 'nonprinting_layer' if not layer_row['printable'] else 'master_layer_not_applied'}); continue
                scanned_layers += 1; layer = layers[layer_row['layer_identity']]
                location = {'scope': scope, 'page_index': None if page_row is None else page_row['page_index'],
                    'page_identity': self._reference_identity(page), 'layer_identity': layer_row['layer_identity'],
                    'layer_name': layer_row['name'], 'applies_to_page_indices': applied,
                    'layer_printable': layer_row['printable'], 'layer_visible': layer_row['visible'],
                    'shape_identity': None, 'static_id': None, 'object_name': None, 'path': []}
                collection = layer.Shapes; count = self._reference_count(collection)
                if count > max_shapes-accessed: issue('shape_budget_exhausted')
                for index in range(1, min(count, max_shapes-accessed)+1):
                    visit(self._collection_item(collection, index), page, layer, {**location, 'path': [{'kind': 'root', 'index': index}]})
                    if accessed >= max_shapes: break
                if self._reference_count(collection) != count: issue('native_layer_membership_changed', location)
        return {'nodes': nodes, 'rasters': rasters, 'issues': issues, 'excluded_layers': excluded,
            'inspected_layers': scanned_layers, 'accessed_shapes': accessed, 'unique_shapes': len(seen)}

    def preflight_document_rasters(self, minimum_dpi=150., include_nonprinting=False, max_shapes=1000):
        if type(minimum_dpi) not in (int, float) or not math.isfinite(minimum_dpi) or not 1 <= minimum_dpi <= 2400:
            raise CorelBridgeError('minimum_dpi must be finite in [1, 2400].', ErrorCode.INVALID_ARGUMENT)
        if type(include_nonprinting) is not bool or type(max_shapes) is not int or not 1 <= max_shapes <= MAX_PREFLIGHT_SHAPES:
            raise CorelBridgeError('Use a boolean include_nonprinting and integer max_shapes in [1, 4096].', ErrorCode.INVALID_ARGUMENT)
        document = self._target_document(); initial_mutation = self._operation_mutation_started
        context = self._raster_context(document)
        before, pages, layers = self._organization_state(document)
        first = self._raster_scan(document, before, pages, layers, minimum_dpi, include_nonprinting, max_shapes)
        middle, pages, layers = self._organization_state(document)
        second = self._raster_scan(document, middle, pages, layers, minimum_dpi, include_nonprinting, max_shapes)
        after, _, _ = self._organization_state(document)
        if not self._same_com_object(self._target_document(), document, strict=True):
            raise CorelBridgeError('Raster preflight target changed during inspection.', ErrorCode.NO_TARGET_DOCUMENT)
        if self._raster_context(document) != context:
            raise CorelBridgeError('Raster preflight could not verify preserved native context.', ErrorCode.COREL_COM_ERROR)
        stable = before == middle == after and first == second
        first_fingerprint, second_fingerprint = fingerprint(first), fingerprint(second)
        issues = first['issues']
        if not stable:
            issues = issues + [{'code': 'document_raster_state_changed_between_scans', 'location': None}]
            for row in first['rasters']:
                row['status'] = 'indeterminate'; row['checks'] = {key: 'indeterminate' for key in row['checks']}
                row['reasons'] = sorted(set(row['reasons'] + ['document_raster_state_changed_between_scans']))
        summary = {key: sum(row['status'] == key for row in first['rasters']) for key in ('passed', 'failed', 'indeterminate')}
        summary['total'] = len(first['rasters'])
        status = 'indeterminate' if not stable else 'failed' if summary['failed'] else 'indeterminate' if issues or summary['indeterminate'] else 'passed' if summary['total'] else 'not_applicable'
        result = {'schema': 'document-raster-preflight-v1', 'bridge_session_id': self._bridge_session_id,
            'document_session_id': self._document_session_id(document), 'minimum_required_dpi': float(minimum_dpi),
            'include_nonprinting': include_nonprinting, 'max_shapes': max_shapes,
            'coverage': {'status': 'partial' if issues else 'complete', 'page_count': len(before['pages']),
                'inspected_layers': first['inspected_layers'], 'accessed_shapes': first['accessed_shapes'],
                'unique_shapes': first['unique_shapes'], 'excluded_layers': first['excluded_layers'], 'issues': issues},
            'inspection_consistency': {'status': 'two_scans_reconciled' if stable else 'changed',
                'structure_before_fingerprint': before['fingerprint'], 'structure_after_fingerprint': after['fingerprint'],
                'first_scan_fingerprint': first_fingerprint, 'second_scan_fingerprint': second_fingerprint},
            'context_preservation': {'verified': True, 'unit_code': context['unit_code'], 'reference_point_code': context['reference_point_code'],
                'dirty': context['dirty'], 'selection_count': len(context['selection_identities'])},
            'rasters': first['rasters'], 'summary': summary, 'overall_status': status,
            'raster_checks_passed': status == 'passed', 'production_ready': False, 'verification_status': 'implemented_unverified',
            'unchecked_checks': ['source_pixel_detail_and_fidelity', 'native_link_cache_freshness', 'color_icc_spot_overprint',
                'export_generated_rasterization', 'visual_fidelity', 'printer_prepress_approval'],
            'warnings': ['Resolution and local linked-file presence cover observed native bitmap objects only; they do not establish print readiness.',
                'Master/PowerClip coordinate semantics, effects and EPS placeholders can remain indeterminate; native and manual verification are deferred.',
                'Document/filesystem state is observed at bounded reads without atomic locks; link files are not read, updated or resolved in CorelDRAW.']}
        result['fingerprint'] = fingerprint(result)
        self._operation_mutation_started = initial_mutation
        return result
