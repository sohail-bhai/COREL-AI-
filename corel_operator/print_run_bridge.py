"""Measured source-preserving repeat copies on independently owned output sheets."""
from __future__ import annotations

from .errors import CorelBridgeError, ErrorCode
from .native_tracking import tracked_mutation
from .print_runs import (UNCHECKED_CHECKS, MAX_REPEAT_SEGMENTS, close_bounds, matrix_map,
    placement_map, tree_nodes, validate_repeat, validate_run_plan, verify_repeat_copy)
from .vector_geometry import seal


def refused(message):
    raise CorelBridgeError(message, ErrorCode.COREL_COM_ERROR)


class PrintRunBridgeMixin:
    def _print_repeat_tree(self, document, shape):
        tree, handles = self._clip_tree(document, shape)
        segments = 0
        for node in tree_nodes(tree):
            native = handles[node['identity']]
            count = self._reference_count(native.Effects)
            if count or not node['supported_payload']:
                raise CorelBridgeError('Repeat artwork contains unsupported containers or live effects.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            node['effects_count'] = count
            if node['clip_children'] and node['contents_locked'] is not True:
                raise CorelBridgeError('Lock PowerClip contents before inspecting a print repeat.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            node['gradient'] = self._gradient_state(document, native)
            if node['fill']['type_code'] not in (0, 1, 2) or node['outline']['type_code'] not in (0, 1) or not node['gradient']['complete']:
                raise CorelBridgeError('Repeat artwork requires readable no/uniform/fountain fills and no/uniform outlines.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            if node['curve'] is not None:
                segments += node['curve']['segment_count']
                if segments > MAX_REPEAT_SEGMENTS:
                    raise CorelBridgeError('Repeat artwork exceeds 10000 measured curve segments.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        return tree, handles, segments

    def inspect_print_repeat(self, object_name='', shape_index=0, object_reference=None):
        document, shape, identity = self._inspection_target(object_name, shape_index, object_reference)
        if identity['object_reference'] is None:
            raise CorelBridgeError('Repeat artwork requires complete session-bound ownership.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        try:
            context = self._raster_context(document)
            structure = self._organization_state(document)[0]
            tree, handles, segments = self._print_repeat_tree(document, shape)
            second, _, second_segments = self._print_repeat_tree(document, shape)
            if tree != second or segments != second_segments or self._organization_state(document)[0] != structure or self._raster_context(document) != context:
                refused('Repeat inspection changed or could not preserve measured native context.')
            repeat = seal({'schema': 'print-repeat-v1', 'object_reference': identity['object_reference'],
                'bounds_inches': tree['transform']['bounds_inches'], 'node_count': len(handles),
                'segment_count': segments, 'tree': tree, 'verification_scope': 'measured_native_repeat',
                'unchecked_checks': list(UNCHECKED_CHECKS)})
            validate_repeat(repeat)
            return {'repeat': repeat, 'verification_status': 'implemented_unverified',
                'warnings': ['Two bounded native scans reconcile measured payload and source context. Visual, pixel, glyph and production acceptance remain pending.']}
        except CorelBridgeError:
            raise
        except Exception as exc:
            raise CorelBridgeError('Could not inspect complete native repeat artwork safely.', ErrorCode.COREL_COM_ERROR) from exc

    def _print_copy_tree(self, document, page, layer, shape, source_ids, used_ids):
        if not self._same_com_object(shape.Page, page, strict=True) or not self._same_com_object(shape.Layer, layer, strict=True):
            refused('A print copy belongs to a foreign output page or layer.')
        if self._vector_layer_members(layer).count(self._reference_identity(shape)) != 1:
            refused('A print copy is not an independently owned output root.')
        tree, handles, _ = self._print_repeat_tree(document, shape)
        identities = set(handles)
        if identities & (source_ids | used_ids):
            refused('Print copies share source objects or another copy.')
        used_ids.update(identities)
        return tree

    def _print_output_membership(self, output, sheets):
        if self._reference_count(output.Pages) != len(sheets):
            refused('Final output page count differs from the complete plan.')
        page_ids = set()
        if self._reference_count(output.MasterPage.Shapes):
            refused('The output contains unexpected master artwork.')
        for page_index, (page, layer, roots) in enumerate(sheets, 1):
            key = self._reference_identity(page)
            if key in page_ids or not self._same_com_object(self._collection_item(output.Pages, page_index), page, strict=True):
                refused('Output sheet identities/order changed.')
            page_ids.add(key)
            expected = {self._reference_identity(root) for root in roots}
            actual = set(self._vector_layer_members(layer))
            if actual != expected or len(actual) != len(roots) or self._reference_count(page.Shapes) != len(roots):
                refused('Final sheet contains missing, duplicate or unexpected artwork.')
            count = self._reference_count(page.Layers)
            if count > 128: refused('Output layer membership exceeds its bounded scope.')
            for index in range(1, count+1):
                candidate = self._collection_item(page.Layers, index)
                if not self._same_com_object(candidate, layer, strict=True) and self._reference_count(candidate.Shapes):
                    refused('Output sheet contains unplanned artwork outside its owned layer.')

    @tracked_mutation
    def execute_print_run(self, plan, approved_fingerprint):
        plan = validate_run_plan(plan, approved_fingerprint)
        repeat = plan['request']['repeat']; reference = repeat['object_reference']
        source_document = self._selector_document('', 0, reference)
        source, _ = self._resolve_object_reference(source_document, reference)
        if self.inspect_print_repeat(object_reference=reference)['repeat'] != repeat:
            raise CorelBridgeError('Source repeat changed after planning; inspect and approve a new plan.', ErrorCode.INVALID_ARGUMENT)
        self._layout_method(source, 'Copy')
        source_context = self._raster_context(source_document)
        source_structure = self._organization_state(source_document)[0]
        source_page = source_document.ActivePage; source_layer = source_page.ActiveLayer
        previous_active = self.app.ActiveDocument; previous_target = self.target_doc
        baseline = {self._reference_identity(doc) for doc in self._open_document_proxies(self.app)}
        source_ids = {node['identity'] for node in tree_nodes(repeat['tree'])}
        output = None; owned = False; command_open = False; clipboard_modified = False
        records = []; sheets = []; used_ids = set()

        def restore_source():
            source_page.Activate(); source_layer.Activate()
            if self._raster_context(source_document) != source_context or self._organization_state(source_document)[0] != source_structure:
                refused('Measured source structure, selection, dirty state or context changed during the print run.')
            if self.inspect_print_repeat(object_reference=reference)['repeat'] != repeat:
                refused('Measured source artwork changed during the print run.')

        try:
            self._note_mutation(); output = self.app.CreateDocument()
            if output is None or self._reference_identity(output) in baseline:
                refused('CorelDRAW did not create an independently owned output document.')
            membership = {self._reference_identity(doc) for doc in self._open_document_proxies(self.app)}
            owned = self._reference_identity(output) in membership
            if membership != baseline | {self._reference_identity(output)}:
                refused('Open document membership changed unexpectedly during output creation.')
            if self._reference_count(output.Pages) != 1: refused('A new print output must begin with one page.')
            output.BeginCommandGroup('AI Print Run'); command_open = True
            with self._in_inches(output, strict_restore=True), self._reference_point(output, strict_restore=True):
                for sheet in plan['sheets']:
                    index = sheet['page_index']; width = sheet['width_inches']; height = sheet['height_inches']
                    if index > 1: output.AddPagesEx(1, width, height)
                    if self._reference_count(output.Pages) != index: refused('Native sheet creation count differs from the plan.')
                    page = self._collection_item(output.Pages, index)
                    page.Activate(); page.SetSize(width, height)
                    layer = page.CreateLayer('Print Run'); layer.Activate()
                    if abs(page.SizeWidth-width) > .00001 or abs(page.SizeHeight-height) > .00001:
                        refused('Native sheet dimensions differ from the approved plan.')
                    source.Page.Activate(); clipboard_modified = True; source.Copy()
                    page.Activate(); layer.Activate(); blueprint = layer.Paste()
                    if self._reference_count(layer.Shapes) != 1: refused('Paste did not create exactly one native repeat root.')
                    if blueprint is None: blueprint = self._collection_item(layer.Shapes, 1)
                    placements = [item for item in plan['placements'] if item['page_index'] == index]
                    copies = [blueprint]
                    # Every duplication precedes placement, preserving a pristine blueprint.
                    for _ in placements[1:]: copies.append(blueprint.Duplicate(0., 0.))
                    sheets.append((page, layer, copies))
                    for placement, shape in zip(placements, copies):
                        before = self._print_copy_tree(output, page, layer, shape, source_ids, used_ids)
                        pasted = before['transform']['bounds_inches']
                        pristine_map = placement_map(repeat['bounds_inches'], {**pasted, 'rotation_degrees': 0})
                        verify_repeat_copy(repeat['tree'], before, pristine_map)
                        if placement['rotation_degrees'] == 90:
                            shape.RotateEx(90., pasted['x']+pasted['width']/2, pasted['y']+pasted['height']/2)
                        shape.Name = placement['object_name']; shape.SetPosition(placement['x'], placement['y'])
                        outer = placement_map(repeat['bounds_inches'], placement)
                        actual_map = placement_map(pasted, placement)
                        matrix = matrix_map(before['transform']['matrix'], actual_map)
                        actual = self._print_repeat_tree(output, shape)[0]
                        verify_repeat_copy(repeat['tree'], actual, outer, placement['object_name'], matrix)
                        if not close_bounds(actual['transform']['bounds_inches'], {k: placement[k] for k in ('x', 'y', 'width', 'height')}):
                            refused('Native repeat placement differs from its approved sheet slot.')
                        records.append((page, layer, shape, placement, matrix))
                self._print_output_membership(output, sheets)
                final_ids = set()
                for page, layer, shape, placement, matrix in records:
                    actual = self._print_copy_tree(output, page, layer, shape, source_ids, final_ids)
                    verify_repeat_copy(repeat['tree'], actual, placement_map(repeat['bounds_inches'], placement), placement['object_name'], matrix)
                    if not close_bounds(actual['transform']['bounds_inches'], {k: placement[k] for k in ('x', 'y', 'width', 'height')}):
                        refused('Final copy geometry changed after other sheet edits.')
                if len(records) != plan['summary']['requested_copies'] or len(final_ids) != plan['summary']['output_shape_count']:
                    refused('Final independent copy or descendant counts differ from the complete plan.')
                for page, _, _ in sheets:
                    if abs(page.SizeWidth-plan['layout']['sheet_width_inches']) > .00001 or abs(page.SizeHeight-plan['layout']['sheet_height_inches']) > .00001:
                        refused('Final sheet dimensions changed during copying.')
            restore_source()
            if {self._reference_identity(doc) for doc in self._open_document_proxies(self.app)} != baseline | {self._reference_identity(output)}:
                refused('Final open document membership differs from the owned output scope.')
            output.EndCommandGroup(); command_open = False
            output.Activate(); sheets[0][0].Activate(); sheets[0][1].Activate()
            self._bind_target_document(output, new_document=True)
            items = []
            for _, _, shape, placement, _ in records[:100]:
                items.append({**{k: placement[k] for k in ('copy_index', 'page_index', 'slot_index', 'object_name')},
                    'object_reference': self._reference_for_shape(output, shape)})
            return {'created': True, 'copy_count': len(records), 'sheet_count': len(sheets),
                'output_shape_count': len(final_ids), 'approved_fingerprint': approved_fingerprint,
                'output_document': {'name': str(output.Name), 'document_session_id': self._document_session_id(output)},
                'sheets': plan['sheets'], 'items': items, 'items_truncated': len(records) > 100,
                'source_preservation': {'verified': True, 'scope': 'measured_native_repeat_and_document_context'},
                'clipboard_modified': clipboard_modified, 'production_ready': False,
                'verification_status': 'implemented_unverified', 'unchecked_checks': list(UNCHECKED_CHECKS),
                'warnings': ['System clipboard contents were replaced by the source repeat copy.',
                    'All requested copies were placed without overage; visual and production acceptance remain pending.']}
        except Exception as exc:
            rollback = {'attempted': True, 'verified': False, 'output_closed': False, 'source_observations_restored': False}
            try:
                if owned and output is not None:
                    if self._reference_identity(output) in baseline: refused('Refusing to discard a pre-existing document.')
                    if command_open: output.EndCommandGroup(); command_open = False
                    output.Dirty = False; output.Close(); rollback['output_closed'] = True
                self._bind_target_document(previous_target)
                restore_source(); rollback['source_observations_restored'] = True
                membership = {self._reference_identity(doc) for doc in self._open_document_proxies(self.app)}
                if previous_active is not None and self._reference_identity(previous_active) in membership: previous_active.Activate()
                rollback['verified'] = membership == baseline
            except Exception as cleanup_error:
                rollback['error_type'] = type(cleanup_error).__name__
            code = exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.COREL_COM_ERROR
            raise CorelBridgeError('Print run could not complete safely. ' + ('Owned output cleanup and measured source state were verified.' if rollback['verified'] else 'Inspect the source and remaining output before reconciliation.'),
                code, {'rollback': rollback, 'clipboard_modified': clipboard_modified}) from exc
