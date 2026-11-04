"""Register the researched native document raster preflight contract."""
from __future__ import annotations
import copy
import csv
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'tests'))
from scripts.update_raster_catalog import obj, nullable, ref
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result, error_result
from raster_preflight_fakes import fixture


def condition(properties, then):
    return {'if': {'properties': properties, 'required': list(properties)}, 'then': then}


def main():
    path = ROOT/'catalog/mcp_tool_registry.json'; registry = json.loads(path.read_text(encoding='utf-8'))
    name = 'preflight_document_rasters'; boolean = {'type': 'boolean'}
    digest = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    count = {'type': 'integer', 'minimum': 0, 'maximum': 4096}
    text = {'type': 'string', 'maxLength': 1000}
    reason = {'type': 'string', 'maxLength': 128}
    status = {'enum': ['passed', 'failed', 'indeterminate']}
    definitions = {
        'raster_preflight_location': obj({'scope': {'enum': ['page', 'master']},
            'page_index': nullable({'type': 'integer', 'minimum': 1, 'maximum': 256}), 'page_identity': digest,
            'layer_identity': digest, 'layer_name': {'type': 'string', 'maxLength': 512},
            'applies_to_page_indices': {'type': 'array', 'items': {'type': 'integer', 'minimum': 1, 'maximum': 256}, 'maxItems': 256, 'uniqueItems': True},
            'layer_printable': boolean, 'layer_visible': boolean, 'shape_identity': nullable(digest),
            'static_id': nullable({'type': 'integer', 'minimum': 0, 'maximum': 2147483647}),
            'object_name': nullable({'type': 'string', 'maxLength': 512}),
            'path': {'type': 'array', 'items': obj({'kind': {'enum': ['root', 'group', 'powerclip']},
                'index': {'type': 'integer', 'minimum': 1, 'maximum': 4096}}), 'maxItems': 34}}),
        'raster_link_presence': obj({'status': {'enum': ['passed', 'failed', 'indeterminate', 'not_applicable']},
            'resolved_path': nullable({'type': 'string', 'minLength': 1, 'maxLength': 32767}),
            'file_bytes': nullable({'type': 'integer', 'minimum': 0}), 'file_state_fingerprint': nullable(digest), 'reason': nullable(reason)}),
        'raster_link_snapshot': obj({'externally_linked': nullable(boolean), 'opi_linked': nullable(boolean),
            'eps_placeholder': nullable(boolean), 'native_filename': nullable({'type': 'string', 'maxLength': 32767}),
            'bitmap_identity': nullable(digest), 'presence': ref('raster_link_presence')}),
        'raster_preflight_row': obj({'location': ref('raster_preflight_location'), 'bitmap': ref('bitmap_metadata'),
            'transform': nullable(ref('bitmap_transform')), 'uncropped_box': nullable(ref('bitmap_uncropped_box')),
            'effective_resolution': ref('bitmap_effective_resolution'),
            'bitmap_consistency': copy.deepcopy(next(t for t in registry['tools'] if t['name']=='get_bitmap_properties')['output_schema']['allOf'][1]['then']['properties']['data']['properties']['inspection_consistency']),
            'link': ref('raster_link_snapshot'), 'checks': obj({'effective_resolution': status,
                'linked_source_presence': {'enum': ['passed', 'failed', 'indeterminate', 'not_applicable']}}),
            'observed_status': status, 'status': status,
            'reasons': {'type': 'array', 'items': reason, 'maxItems': 64, 'uniqueItems': True}}),
        'raster_preflight_result': obj({'schema': {'const': 'document-raster-preflight-v1'},
            'bridge_session_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'},
            'document_session_id': {'type': 'string', 'pattern': '^doc-[0-9]{4,16}$'},
            'minimum_required_dpi': {'type': 'number', 'minimum': 1, 'maximum': 2400}, 'include_nonprinting': boolean,
            'max_shapes': {'type': 'integer', 'minimum': 1, 'maximum': 4096},
            'coverage': obj({'status': {'enum': ['complete', 'partial']}, 'page_count': {'type': 'integer', 'minimum': 1, 'maximum': 256},
                'inspected_layers': count, 'accessed_shapes': count, 'unique_shapes': count,
                'excluded_layers': {'type': 'array', 'items': obj({'layer_identity': digest,
                    'reason': {'enum': ['nonprinting_layer', 'master_layer_not_applied']}}), 'maxItems': 4096},
                'issues': {'type': 'array', 'items': obj({'code': reason, 'location': nullable(ref('raster_preflight_location'))}), 'maxItems': 4098}}),
            'inspection_consistency': obj({'status': {'enum': ['two_scans_reconciled', 'changed']},
                'structure_before_fingerprint': digest, 'structure_after_fingerprint': digest,
                'first_scan_fingerprint': digest, 'second_scan_fingerprint': digest}),
            'context_preservation': obj({'verified': {'const': True}, 'unit_code': {'type': 'integer', 'minimum': 0, 'maximum': 2147483647},
                'reference_point_code': {'type': 'integer', 'minimum': 0, 'maximum': 2147483647}, 'dirty': boolean, 'selection_count': count}),
            'rasters': {'type': 'array', 'items': ref('raster_preflight_row'), 'maxItems': 4096},
            'summary': obj({key: count for key in ('passed', 'failed', 'indeterminate', 'total')}),
            'overall_status': {'enum': ['passed', 'failed', 'indeterminate', 'not_applicable']},
            'raster_checks_passed': boolean, 'production_ready': {'const': False}, 'verification_status': {'const': 'implemented_unverified'},
            'unchecked_checks': {'type': 'array', 'items': reason, 'minItems': 6, 'maxItems': 6, 'uniqueItems': True},
            'warnings': {'type': 'array', 'items': text, 'maxItems': 20}, 'fingerprint': digest}),
    }
    definitions['raster_link_presence']['allOf'] = [condition({'status': {'const': 'passed'}}, {'properties': {
        'resolved_path': {'type': 'string', 'minLength': 1}, 'file_bytes': {'type': 'integer', 'minimum': 1},
        'file_state_fingerprint': digest, 'reason': {'const': None}}})]
    definitions['raster_preflight_row']['allOf'] = [condition({'status': {'const': 'passed'}}, {'properties': {
        'observed_status': {'const': 'passed'}, 'checks': {'properties': {'effective_resolution': {'const': 'passed'},
            'linked_source_presence': {'enum': ['passed', 'not_applicable']}}},
        'effective_resolution': {'properties': {'status': {'const': 'calculated'}, 'resolution_check': {'const': 'pass'}}},
        'bitmap_consistency': {'properties': {'status': {'const': 'two_reads_reconciled'}}},
        'link': {'properties': {'eps_placeholder': {'const': False}}}}})]
    definitions['raster_preflight_result']['allOf'] = [
        condition({'overall_status': {'const': 'passed'}}, {'properties': {'raster_checks_passed': {'const': True},
            'coverage': {'properties': {'status': {'const': 'complete'}, 'issues': {'maxItems': 0}}},
            'inspection_consistency': {'properties': {'status': {'const': 'two_scans_reconciled'}}},
            'summary': {'properties': {'failed': {'const': 0}, 'indeterminate': {'const': 0}, 'total': {'minimum': 1}}},
            'rasters': {'minItems': 1, 'items': {'properties': {'status': {'const': 'passed'}}}}}}),
        condition({'overall_status': {'enum': ['failed', 'indeterminate', 'not_applicable']}}, {'properties': {'raster_checks_passed': {'const': False}}}),
        condition({'overall_status': {'const': 'failed'}}, {'properties': {'summary': {'properties': {'failed': {'minimum': 1}}},
            'inspection_consistency': {'properties': {'status': {'const': 'two_scans_reconciled'}}}}}),
        condition({'overall_status': {'const': 'not_applicable'}}, {'properties': {'summary': {'properties': {'total': {'const': 0}}},
            'coverage': {'properties': {'status': {'const': 'complete'}}}}}),
        condition({'raster_checks_passed': {'const': True}}, {'properties': {'overall_status': {'const': 'passed'}}}),
    ]
    registry['schema_definitions'].update(definitions)
    api = sorted(set(next(t for t in registry['tools'] if t['name']=='get_bitmap_properties')['api_requirements'] +
        next(t for t in registry['tools'] if t['name']=='get_document_structure')['api_requirements'] +
        ['Bitmap.LinkFileName', 'Bitmap.OPILinked', 'Bitmap.IsEPS', 'Shape.ParentGroup', 'Shape.PowerClipParent', 'PowerClip.Parent', 'PowerClip.Shapes', 'Document.Dirty', 'Document.SelectionRange']))
    tool = copy.deepcopy(next(t for t in registry['tools'] if t['name']=='get_bitmap_properties'))
    tool.update(name=name, category='images', description='Two bounded whole-document graph scans reconcile native raster DPI and local linked-file presence without changing native context.', api_requirements=api)
    tool['implementation']['bridge_method'] = name
    tool['input_schema'] = obj({'minimum_dpi': {'type': 'number', 'minimum': 1, 'maximum': 2400, 'default': 150.},
        'include_nonprinting': {**boolean, 'default': False}, 'max_shapes': {'type': 'integer', 'minimum': 1, 'maximum': 4096, 'default': 1000}}, [])
    tool['output_schema']['allOf'][1]['then']['properties']['data'] = ref('raster_preflight_result')
    tool['test_evidence'] = {'status': 'mock_com_passed', 'sources': ['tests/test_raster_preflight.py', 'tests/integration/test_corel_live.py',
        'docs/RASTER_PREFLIGHT.md', 'docs/x7_raster_preflight_api_evidence.json', 'docs/raster_preflight_online_evidence.json']}
    tool['known_limitations'] = ['Native/manual verification remains deferred; all results remain implemented_unverified.',
        'Default 1000/access limit 4096 shapes, 32 nesting levels; structure itself is limited to 256 pages/128 layers/4096 entries.',
        'Native bitmap objects only; export-generated rasterization, source detail/fidelity, cache freshness, ICC/spot/overprint and prepress remain unchecked.',
        'Master/PowerClip/effect/unknown/EPS geometry stays indeterminate; opaque symbol/OLE/EPS/custom containers and special effect groups prevent clean coverage.',
        'Local link presence only; no source decoding or native link resolve/update. Remote/device links and relative base semantics remain indeterminate.',
        'Nonprinting layers are excluded by default and reported; hidden printable layers are included. Master bitmaps are recorded once with applied-page indices.',
        'Native and filesystem reads are bounded observations without atomic locking.']
    registry['tools'] = [t for t in registry['tools'] if t['name'] != name] + [tool]
    bridge, _, _, _ = fixture()
    registry['tool_examples'][name] = {'request': {'minimum_dpi': 150.},
        'success': success_result(name, bridge.preflight_document_rasters(), 1),
        'error': error_result(name, CorelBridgeError('Raster preflight request was refused.', ErrorCode.INVALID_ARGUMENT), 1)}
    path.write_text(json.dumps(registry, indent=2)+'\n', encoding='utf-8')
    inventory_path = ROOT/'catalog/coreldraw_x7_api_inventory.json'
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    evidence_id = 'x7_raster_preflight'
    inventory['evidence_sources'] = [s for s in inventory['evidence_sources'] if s['id'] != evidence_id] + [{
        'id': evidence_id, 'type': 'installed_type_library', 'path': 'docs/x7_raster_preflight_api_evidence.json',
        'inspection_date': datetime.date.today().isoformat(), 'description': '24 link/ownership/page/layer descriptors, no application access.'}]
    known = {m['id']: m for m in inventory['members']}
    for member in api:
        if member not in known:
            owner, property_name = member.split('.')
            value = {'id': member, 'owner': owner, 'kind': 'property', 'access': 'read_only', 'signature': property_name,
                'status': 'typelib_confirmed', 'used_by': [name], 'evidence': [evidence_id],
                'docs_url': f'https://community.coreldraw.com/sdk/api/draw/17/p/{member.lower()}', 'live_test_status': 'not_run_deferred'}
            inventory['members'].append(value); known[member] = value
        else: known[member]['used_by'] = list(dict.fromkeys(known[member].get('used_by', []) + [name]))
    inventory_path.write_text(json.dumps(inventory, indent=2)+'\n', encoding='utf-8')
    enum_path = ROOT/'catalog/enum_reference.json'; enums = json.loads(enum_path.read_text(encoding='utf-8'))
    shape_enum = enums['enums']['cdrShapeType']
    shape_enum['bridge_usage'] = list(dict.fromkeys(shape_enum.get('bridge_usage', []) + [name]))
    enum_path.write_text(json.dumps(enums, indent=2)+'\n', encoding='utf-8')
    matrix_path = ROOT/'catalog/capability_matrix.csv'
    with matrix_path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = [row for row in reader if row['tool_name'] != name]
    rows.append(dict(zip(fields, ['tool.'+name, 'approved_atomic', 'images', name, 'registered', 'implemented_unverified',
        'read_only', 'P1', 'research_reference', 'confirmed', 'not_run_deferred', 'not_required',
        'Native coordinates/linked-source freshness/color/export rasterization and visual prepress remain unresolved.',
        'Disposable two-page/group raster gate and prepared-image CDR/PDF review; clipping/master/link cases require native/manual expansion'])))
    with matrix_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps_path = ROOT/'catalog/workflow_gaps.json'; gaps = json.loads(gaps_path.read_text(encoding='utf-8'))
    for gap in gaps['gaps']:
        if gap['id'] not in ('images', 'export_prepress'): continue
        gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + [name]))
        if gap['id'] == 'images': gap['source_ids'] = list(dict.fromkeys(gap['source_ids'] + ['preflight']))
        gap['evidence'] = list(dict.fromkeys(gap.get('evidence', []) + ['docs/RASTER_PREFLIGHT.md', 'tests/test_raster_preflight.py']))
        gap['missing_behavior'] = [item.replace('Document-wide native raster preflight and source-detail/color/visual verification',
            'Native/source-detail/color/visual raster acceptance and export-generated rasterization coverage').replace(
            'Document-wide raster preflight and native/source-detail/visual/prepress verification',
            'Native/source-detail/visual/prepress raster acceptance and export-generated rasterization coverage') for item in gap['missing_behavior']]
    gaps_path.write_text(json.dumps(gaps, indent=2)+'\n', encoding='utf-8')
    print('Registered document raster preflight, five strict definitions and researched API dependencies.')


if __name__ == '__main__': main()
