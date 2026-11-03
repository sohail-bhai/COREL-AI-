"""Bounded document structure and fingerprint-guarded page/layer controls."""
from __future__ import annotations

import copy
import math
import re

from .errors import CorelBridgeError, ErrorCode
from .native_tracking import tracked_mutation
from .vector_geometry import fingerprint

MAX_ORGANIZATION_PAGES = 256
MAX_ORGANIZATION_LAYERS = 128
MAX_ORGANIZATION_ITEMS = 4096


def organization_name(value):
    if type(value) is not str or not value.strip() or len(value) > 128 or any(ord(c) < 32 for c in value):
        raise CorelBridgeError('Names must contain 1-128 characters without control characters.', ErrorCode.INVALID_ARGUMENT)
    return value


class OrganizationBridgeMixin:
    def _organization_state(self, document):
        pages = {}; layers = {}; objects = set(); remaining = MAX_ORGANIZATION_ITEMS
        mutation_started = self._operation_mutation_started

        def members(collection, maximum):
            nonlocal remaining
            count = self._reference_count(collection)
            if count > maximum or count > remaining:
                raise CorelBridgeError('Document structure exceeds the bounded page/layer/object budget.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            remaining -= count
            values = [self._collection_item(collection, i) for i in range(1, count + 1)]
            identities = [self._reference_identity(value) for value in values]
            if len(set(identities)) != len(identities):
                raise CorelBridgeError('Document structure contains ambiguous native identities.', ErrorCode.AMBIGUOUS_SELECTOR)
            return values

        def layer_state(layer, owner):
            key = self._reference_identity(layer)
            if key in layers or not self._same_com_object(layer.Page, owner, strict=True):
                raise CorelBridgeError('Layer ownership is ambiguous or foreign.', ErrorCode.COREL_COM_ERROR)
            value = {'layer_identity': key, 'name': layer.Name}
            if type(value['name']) is not str or len(value['name']) > 512:
                raise CorelBridgeError('Layer name is unavailable or too large.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            for field, native in [('visible', 'Visible'), ('editable', 'Editable'), ('printable', 'Printable'), ('master', 'Master'), ('is_special', 'IsSpecialLayer')]:
                value[field] = getattr(layer, native)
                if type(value[field]) is not bool:
                    raise CorelBridgeError('Layer state requires readable native boolean flags.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            roots = members(layer.Shapes, MAX_ORGANIZATION_ITEMS)
            value['root_shape_identities'] = [self._reference_identity(shape) for shape in roots]
            for shape, shape_key in zip(roots, value['root_shape_identities']):
                if shape_key in objects or not self._same_com_object(shape.Layer, layer, strict=True) or not self._same_com_object(shape.Page, owner, strict=True):
                    raise CorelBridgeError('Root shape ownership is ambiguous or foreign.', ErrorCode.COREL_COM_ERROR)
                objects.add(shape_key)
            layers[key] = layer
            return value

        try:
            previous_unit = document.Unit
            if type(previous_unit) is not int:
                raise CorelBridgeError('Document unit metadata is unavailable.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            master = document.MasterPage
            master_key = self._reference_identity(master)
            master_layers = [layer_state(layer, master) for layer in members(master.Layers, MAX_ORGANIZATION_LAYERS)]
            master_ids = {row['layer_identity'] for row in master_layers}
            result_pages = []
            with self._in_inches(document, strict_restore=True):
                if document.Unit != self.CDR_INCH:
                    raise CorelBridgeError('Native page inspection did not enter inch units.', ErrorCode.COREL_COM_ERROR)
                for index, page in enumerate(members(document.Pages, MAX_ORGANIZATION_PAGES), 1):
                    key = self._reference_identity(page)
                    if key == master_key or key in pages or type(page.Index) is not int or page.Index != index:
                        raise CorelBridgeError('Native page identity/index is inconsistent.', ErrorCode.COREL_COM_ERROR)
                    width, height = page.SizeWidth, page.SizeHeight
                    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (width, height)):
                        raise CorelBridgeError('Page dimensions are unavailable.', ErrorCode.UNSUPPORTED_IN_PROFILE)
                    if type(page.Name) is not str or len(page.Name) > 512:
                        raise CorelBridgeError('Page name is unavailable or too large.', ErrorCode.UNSUPPORTED_IN_PROFILE)
                    local = [layer_state(layer, page) for layer in members(page.Layers, MAX_ORGANIZATION_LAYERS)]
                    local_ids = {row['layer_identity'] for row in local}
                    all_layers = members(page.AllLayers, 2 * MAX_ORGANIZATION_LAYERS)
                    all_ids = [self._reference_identity(layer) for layer in all_layers]
                    if not local_ids <= set(all_ids) or not set(all_ids) <= local_ids | master_ids:
                        raise CorelBridgeError('AllLayers contains unaccounted page/master membership.', ErrorCode.COREL_COM_ERROR)
                    active_layer = self._reference_identity(page.ActiveLayer)
                    if active_layer not in all_ids:
                        raise CorelBridgeError('Active layer is outside its page scope.', ErrorCode.COREL_COM_ERROR)
                    result_pages.append({'page_identity': key, 'page_index': index, 'name': page.Name,
                        'width_inches': float(width), 'height_inches': float(height), 'active_layer_identity': active_layer,
                        'layers': local, 'all_layer_identities': all_ids})
                    pages[key] = page
            if type(document.Unit) is not int or document.Unit != previous_unit:
                raise CorelBridgeError('Document unit restoration could not be verified.', ErrorCode.COREL_COM_ERROR)
            active = self._reference_identity(document.ActivePage)
            if not pages or active not in pages:
                raise CorelBridgeError('Active page is outside the document.', ErrorCode.COREL_COM_ERROR)
            state = {'schema': 'document-structure-v1', 'document_session_id': self._document_session_id(document),
                'bridge_session_id': self._bridge_session_id, 'active_page_identity': active,
                'pages': result_pages, 'master_layers': master_layers}
            state['fingerprint'] = fingerprint(state)
            self._organization_scan_count = MAX_ORGANIZATION_ITEMS - remaining
            # The only native setters in a successful inspection are temporary
            # unit changes, whose final state has now been read back exactly.
            self._operation_mutation_started = mutation_started
            return state, pages, layers
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError('Could not inspect complete bounded page/layer structure.', ErrorCode.UNSUPPORTED_IN_PROFILE) from exc

    def get_document_structure(self):
        state, _, _ = self._organization_state(self._target_document())
        return {'structure': state, 'verification_status': 'implemented_unverified'}

    def _organization_guard(self, expected_fingerprint):
        if type(expected_fingerprint) is not str or re.fullmatch(r'[0-9a-f]{64}', expected_fingerprint) is None:
            raise CorelBridgeError('Supply the current get_document_structure fingerprint.', ErrorCode.INVALID_ARGUMENT)
        document = self._target_document()
        state, pages, layers = self._organization_state(document)
        if expected_fingerprint != state['fingerprint']:
            raise CorelBridgeError('Document structure changed; inspect it again before editing.', ErrorCode.INVALID_ARGUMENT)
        return document, state, pages, layers

    @staticmethod
    def _organization_page(state, page_identity):
        if type(page_identity) is not str:
            raise CorelBridgeError('page_identity must be a string from structure inspection.', ErrorCode.INVALID_ARGUMENT)
        row = next((page for page in state['pages'] if page['page_identity'] == page_identity), None)
        if row is None:
            raise CorelBridgeError('Page identity no longer belongs to this document.', ErrorCode.OBJECT_NOT_FOUND)
        return row

    def _organization_layer(self, state, page_identity, layer_identity):
        page = self._organization_page(state, page_identity)
        if type(layer_identity) is not str:
            raise CorelBridgeError('layer_identity must be a string from structure inspection.', ErrorCode.INVALID_ARGUMENT)
        layer = next((row for row in page['layers'] if row['layer_identity'] == layer_identity), None)
        if layer is None:
            raise CorelBridgeError('Layer identity is not local to the requested page.', ErrorCode.OBJECT_NOT_FOUND)
        if layer['master'] or layer['is_special']:
            raise CorelBridgeError('Editing master or special layers is deferred.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        return layer

    @staticmethod
    def _organization_plain(state):
        return {key: value for key, value in state.items() if key != 'fingerprint'}

    def _organization_verify(self, actual, expected):
        if self._organization_plain(actual) != self._organization_plain(expected):
            raise CorelBridgeError('Native structure readback differs from the exact requested change.', ErrorCode.COREL_COM_ERROR)

    def _organization_result(self, before, after, **extra):
        return {'updated': before['fingerprint'] != after['fingerprint'], 'before_fingerprint': before['fingerprint'],
            'structure': after, 'verification_status': 'implemented_unverified', **extra}

    def _organization_error(self, exc, rollback=None):
        raise CorelBridgeError('Page/layer operation could not complete with verified structure readback.',
            exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR,
            {'rollback': rollback or {'attempted': False, 'verified': False}, 'recovery_required': not bool(rollback and rollback.get('verified'))}) from exc

    @tracked_mutation
    def activate_page(self, page_identity, expected_fingerprint):
        document, before, pages, _ = self._organization_guard(expected_fingerprint)
        self._organization_page(before, page_identity)
        expected = copy.deepcopy(before); expected['active_page_identity'] = page_identity
        try:
            if page_identity != before['active_page_identity']:
                self._note_mutation(); self._layout_method(pages[page_identity], 'Activate')()
            after, _, _ = self._organization_state(document)
            self._organization_verify(after, expected)
            return self._organization_result(before, after)
        except Exception as exc:
            self._organization_error(exc)

    @tracked_mutation
    def activate_layer(self, page_identity, layer_identity, expected_fingerprint):
        document, before, pages, layers = self._organization_guard(expected_fingerprint)
        row = self._organization_layer(before, page_identity, layer_identity)
        if not row['visible'] or not row['editable']:
            raise CorelBridgeError('Enable visibility and editing explicitly before activating this layer.', ErrorCode.INVALID_ARGUMENT)
        expected = copy.deepcopy(before); expected['active_page_identity'] = page_identity
        self._organization_page(expected, page_identity)['active_layer_identity'] = layer_identity
        try:
            if page_identity != before['active_page_identity']:
                self._note_mutation(); self._layout_method(pages[page_identity], 'Activate')()
            if not self._same_com_object(pages[page_identity].ActiveLayer, layers[layer_identity], strict=True):
                self._note_mutation(); self._layout_method(layers[layer_identity], 'Activate')()
            after, _, _ = self._organization_state(document)
            self._organization_verify(after, expected)
            return self._organization_result(before, after)
        except Exception as exc:
            self._organization_error(exc)

    @tracked_mutation
    def rename_page(self, page_identity, name, expected_fingerprint):
        organization_name(name)
        document, before, pages, _ = self._organization_guard(expected_fingerprint)
        row = self._organization_page(before, page_identity)
        if any(p['page_identity'] != page_identity and p['name'].casefold() == name.casefold() for p in before['pages']):
            raise CorelBridgeError('A page with that name already exists.', ErrorCode.INVALID_ARGUMENT)
        expected = copy.deepcopy(before); self._organization_page(expected, page_identity)['name'] = name
        try:
            if row['name'] != name:
                self._note_mutation(); pages[page_identity].Name = name
            after, _, _ = self._organization_state(document)
            self._organization_verify(after, expected)
            return self._organization_result(before, after)
        except Exception as exc:
            self._organization_error(exc)

    @tracked_mutation
    def set_layer_properties(self, page_identity, layer_identity, properties, expected_fingerprint):
        if type(properties) is not dict or not properties or not set(properties) <= {'name', 'visible', 'editable', 'printable'}:
            raise CorelBridgeError('Supply one or more of name, visible, editable and printable.', ErrorCode.INVALID_ARGUMENT)
        if 'name' in properties:
            organization_name(properties['name'])
        if any(type(value) is not bool for key, value in properties.items() if key != 'name'):
            raise CorelBridgeError('Layer flags must be booleans.', ErrorCode.INVALID_ARGUMENT)
        document, before, _, layers = self._organization_guard(expected_fingerprint)
        row = self._organization_layer(before, page_identity, layer_identity)
        page = self._organization_page(before, page_identity)
        if 'name' in properties and any(x['layer_identity'] != layer_identity and x['name'].casefold() == properties['name'].casefold()
            for x in page['layers'] + before['master_layers']):
            raise CorelBridgeError('A local/master layer with that name already exists.', ErrorCode.INVALID_ARGUMENT)
        expected = copy.deepcopy(before); self._organization_layer(expected, page_identity, layer_identity).update(properties)
        try:
            for key, native in [('name', 'Name'), ('visible', 'Visible'), ('printable', 'Printable'), ('editable', 'Editable')]:
                if key in properties and properties[key] != row[key]:
                    self._note_mutation(); setattr(layers[layer_identity], native, properties[key])
            after, _, _ = self._organization_state(document)
            self._organization_verify(after, expected)
            return self._organization_result(before, after)
        except Exception as exc:
            self._organization_error(exc)

    def _organization_restore_context(self, document, before, pages, layers, affected_page=None):
        if affected_page is not None:
            row = self._organization_page(before, affected_page)
            if not self._same_com_object(pages[affected_page].ActiveLayer, layers[row['active_layer_identity']], strict=True):
                self._note_mutation(); self._layout_method(layers[row['active_layer_identity']], 'Activate')()
        original = before['active_page_identity']
        if not self._same_com_object(document.ActivePage, pages[original], strict=True):
            self._note_mutation(); self._layout_method(pages[original], 'Activate')()

    def _organization_without_created(self, actual, before, kind, key, page_identity=None):
        result = copy.deepcopy(actual)
        allowed_active = {before['active_page_identity'], key if kind == 'page' else page_identity}
        if actual['active_page_identity'] not in allowed_active:
            raise CorelBridgeError('Creation unexpectedly activated another existing page.', ErrorCode.COREL_COM_ERROR)
        result['active_page_identity'] = before['active_page_identity']
        if kind == 'page':
            if len(result['pages']) != len(before['pages']) + 1 or result['pages'][-1]['page_identity'] != key:
                raise CorelBridgeError('Page creation did not append exactly one owned page.', ErrorCode.COREL_COM_ERROR)
            created = result['pages'].pop()
            if any(row['root_shape_identities'] for row in created['layers']):
                raise CorelBridgeError('New page contains unexpected local artwork; deletion is refused.', ErrorCode.COREL_COM_ERROR)
        else:
            row = self._organization_page(result, page_identity)
            created = next((layer for layer in row['layers'] if layer['layer_identity'] == key), None)
            if created is None or created['root_shape_identities'] or created['master'] or created['is_special']:
                raise CorelBridgeError('New layer is not an owned empty ordinary local layer.', ErrorCode.COREL_COM_ERROR)
            row['layers'].remove(created)
            row['all_layer_identities'] = [identity for identity in row['all_layer_identities'] if identity != key]
            row['active_layer_identity'] = self._organization_page(before, page_identity)['active_layer_identity']
        self._organization_verify(result, before)
        return created

    def _organization_create(self, document, before, pages, layers, kind, create, configure, page_identity=None):
        receipt = None; key = None; opened = False; close_failed = False; begin_failed = False
        try:
            self._note_mutation()
            try:
                document.BeginCommandGroup('AI Create ' + kind.title()); opened = True
            except Exception:
                begin_failed = True
                raise
            self._note_mutation(); receipt = create()
            key = self._reference_identity(receipt)
            if key in pages or key in layers:
                raise CorelBridgeError('Native creation returned an existing object.', ErrorCode.COREL_COM_ERROR)
            actual, current_pages, current_layers = self._organization_state(document)
            expected_receipt = current_pages.get(key) if kind == 'page' else current_layers.get(key)
            if expected_receipt is None or not self._same_com_object(expected_receipt, receipt, strict=True):
                raise CorelBridgeError('Native creation receipt is outside the bound document.', ErrorCode.COREL_COM_ERROR)
            self._organization_without_created(actual, before, kind, key, page_identity)
            configure(receipt)
            self._organization_restore_context(document, before, pages, layers, page_identity)
            after, _, _ = self._organization_state(document)
            if after['active_page_identity'] != before['active_page_identity'] or (page_identity is not None and
                self._organization_page(after, page_identity)['active_layer_identity'] != self._organization_page(before, page_identity)['active_layer_identity']):
                raise CorelBridgeError('Creation did not restore the previous active page/layer.', ErrorCode.COREL_COM_ERROR)
            created = self._organization_without_created(after, before, kind, key, page_identity)
            opened = False
            try:
                document.EndCommandGroup()
            except Exception:
                close_failed = True
                raise
            final, _, _ = self._organization_state(document)
            self._organization_verify(final, after)
            return self._organization_result(before, after, **{'created_' + kind + '_identity': key}), created
        except Exception as exc:
            rollback = {'attempted': False, 'verified': False}
            try:
                if receipt is not None and key not in pages and key not in layers:
                    actual, current_pages, current_layers = self._organization_state(document)
                    native = current_pages.get(key) if kind == 'page' else current_layers.get(key)
                    if native is None or not self._same_com_object(native, receipt, strict=True):
                        raise CorelBridgeError('Failed creation receipt is not owned.', ErrorCode.COREL_COM_ERROR)
                    self._organization_without_created(actual, before, kind, key, page_identity)
                    rollback['attempted'] = True
                    self._note_mutation(); self._layout_method(receipt, 'Delete')()
                self._organization_restore_context(document, before, pages, layers, page_identity)
                actual, _, _ = self._organization_state(document)
                self._organization_verify(actual, before)
                rollback['verified'] = True
            except Exception as cleanup:
                rollback['error_type'] = type(cleanup).__name__
            if opened:
                opened = False
                try:
                    document.EndCommandGroup()
                except Exception as close_error:
                    rollback['verified'] = False; rollback['command_group_error_type'] = type(close_error).__name__
            if close_failed:
                rollback['verified'] = False; rollback['command_group_close_failed'] = True
            if begin_failed:
                rollback['verified'] = False; rollback['command_group_begin_failed'] = True
            self._organization_error(exc, rollback)

    @tracked_mutation
    def create_page(self, name, width_inches, height_inches, expected_fingerprint):
        organization_name(name)
        if any(type(v) not in (int, float) or not math.isfinite(v) or not .01 <= v <= 2000 for v in (width_inches, height_inches)):
            raise CorelBridgeError('Page dimensions must be finite inches in [0.01, 2000].', ErrorCode.INVALID_ARGUMENT)
        document, before, pages, layers = self._organization_guard(expected_fingerprint)
        if len(pages) >= MAX_ORGANIZATION_PAGES:
            raise CorelBridgeError('The bounded 256-page limit is reached.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if self._organization_scan_count + 1 + 2 * MAX_ORGANIZATION_LAYERS + len(before['master_layers']) > MAX_ORGANIZATION_ITEMS:
            raise CorelBridgeError('Insufficient scan capacity for a new page with bounded native default layers.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if any(row['name'].casefold() == name.casefold() for row in before['pages']):
            raise CorelBridgeError('A page with that name already exists.', ErrorCode.INVALID_ARGUMENT)
        add = self._layout_method(document, 'AddPages')

        def configure(page):
            self._note_mutation(); page.Name = name
            with self._in_inches(document, strict_restore=True):
                self._note_mutation(); self._layout_method(page, 'SetSize')(width_inches, height_inches)
            with self._in_inches(document, strict_restore=True):
                if page.Name != name or any(not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-8)
                    for a, b in ((page.SizeWidth, width_inches), (page.SizeHeight, height_inches))):
                    raise CorelBridgeError('New page name/size differs from the request.', ErrorCode.COREL_COM_ERROR)

        result, _ = self._organization_create(document, before, pages, layers, 'page', lambda: add(1), configure)
        return result

    @tracked_mutation
    def create_layer(self, page_identity, name, expected_fingerprint):
        organization_name(name)
        document, before, pages, layers = self._organization_guard(expected_fingerprint)
        page = self._organization_page(before, page_identity)
        if len(page['layers']) >= MAX_ORGANIZATION_LAYERS:
            raise CorelBridgeError('The bounded 128 local-layer limit is reached.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if self._organization_scan_count + 2 > MAX_ORGANIZATION_ITEMS:
            raise CorelBridgeError('Insufficient scan capacity for new local/AllLayers membership.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        if any(row['name'].casefold() == name.casefold() for row in page['layers'] + before['master_layers']):
            raise CorelBridgeError('A local/master layer with that name already exists.', ErrorCode.INVALID_ARGUMENT)
        create = self._layout_method(pages[page_identity], 'CreateLayer')

        def configure(layer):
            if layer.Name != name:
                raise CorelBridgeError('New layer name differs from the request.', ErrorCode.COREL_COM_ERROR)

        result, _ = self._organization_create(document, before, pages, layers, 'layer', lambda: create(name), configure, page_identity)
        return result
