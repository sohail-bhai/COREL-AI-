"""Register editable paragraph fitting with explicit native and preservation scope."""
import copy
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def write(path, data):
    (ROOT / path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}


def main():
    registry = read('catalog/mcp_tool_registry.json')
    original = next(t for t in registry['tools'] if t['name'] == 'set_text_spacing')
    tool = copy.deepcopy(original)
    tool.update(name='fit_paragraph_text', description='Fit an independent editable paragraph copy using bounded native size/overflow probes and preserve the source.')
    tool['implementation']['bridge_method'] = 'CorelBridge.fit_paragraph_text'
    size = {'type': 'number', 'minimum': 1, 'maximum': 500}
    number = {'type': 'number', 'minimum': .01, 'maximum': 1}
    tool['input_schema'] = obj({'object_reference': {'$ref': '#/schema_definitions/object_reference'},
        'minimum_size_points': dict(size, default=8), 'size_tolerance_points': dict(number, default=.1),
        'result_name': {'type': 'string', 'maxLength': 120, 'pattern': '^[^\\u0000-\\u001f]*$', 'default': ''}}, ['object_reference'])
    hash_schema = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    registry['schema_definitions']['paragraph_fit_probe'] = obj({
        'requested_size_points': size, 'actual_size_points': size, 'overflow': {'type': 'boolean'}})
    data = obj({'created': {'const': True}, 'object': {'$ref': '#/schema_definitions/inspection_identity'},
        'actual_bounds_inches': {'$ref': '#/schema_definitions/bounds_inches'},
        'original_size_points': size, 'minimum_size_points': size, 'actual_size_points': size,
        'overflow': {'const': False}, 'probe_count': {'type': 'integer', 'minimum': 0, 'maximum': 24},
        'probes': {'type': 'array', 'maxItems': 24, 'items': {'$ref': '#/schema_definitions/paragraph_fit_probe'}},
        'size_tolerance_points': number, 'search_scope': {'const': 'largest_verified_probe_under_bounded_overflow_search'},
        'content_sha256': hash_schema, 'source_preservation': obj({'verified': {'const': True},
            'scope': {'const': 'root_membership_relative_order_measured_source_text_frame_basic_appearance'}, 'source_sha256': hash_schema}),
        'verification_status': {'const': 'implemented_unverified'},
        'warnings': {'type': 'array', 'maxItems': 10, 'items': {'type': 'string', 'maxLength': 1000}}})
    tool['output_schema']['allOf'][1]['then']['properties']['data'] = data
    added = ['Text.Frame', 'TextFrame.FrameShape', 'TextFrame.IsInsideContainer', 'TextFrame.IsFittedToPath',
             'TextFrame.VerticalAlignment', 'TextFrame.ColumnCount', 'TextFrame.ColumnWidth', 'TextFrame.ColumnGutter',
             'TextFrame.Fill', 'TextFrame.Outline']
    common = next(t for t in registry['tools'] if t['name'] == 'create_powerclip')['api_requirements']
    unused = {'Application.CreateShapeRange', 'ShapeRange.Add', 'ShapeRange.Group', 'Shape.AddToPowerClip',
              'Shape.SetSize', 'Shape.SetPosition', 'PowerClip.ExtractShapes', 'TextRange.SetLineSpacing'}
    tool['api_requirements'] = sorted((set(common) | set(original['api_requirements']) | set(added) | {'Shape.Effects'}) - unused)
    tool['test_evidence']['sources'] = ['tests/test_text_fitting.py', 'docs/TEXT_FITTING.md', 'docs/x7_text_range_evidence.json']
    tool['known_limitations'] = [
        'Native and manual typography acceptance remain deferred to the consolidated campaign.',
        'One exact root paragraph, ordinary frame, uniform readable basic style and spacing; up to 10000 characters and 1000 ownership nodes.',
        'No enlargement, frame resizing, per-run fitting, linked/path/container text or automatic template reflow.',
        'Measured overflow is not glyph/visual/safe-area fit or globally optimal font size.',
        'Receipt-matching independent copies are cleaned up; shared/moved/changed/uncertain objects remain explicit and quarantined.']
    registry['tools'] = [t for t in registry['tools'] if t['name'] != tool['name']] + [tool]
    example = copy.deepcopy(registry['tool_examples']['set_text_style'])
    reference = copy.deepcopy(example['success']['data']['object']['object_reference'])
    example['request'] = {'object_reference': reference, 'minimum_size_points': 8}
    example['success']['tool'] = example['error']['tool'] = tool['name']
    identity = copy.deepcopy(example['success']['data']['object'])
    identity.update(object_name='FittedCopy', static_id=102, object_id='doc-0001:shape:102', shape_index=2)
    identity['object_reference'].update(object_name='FittedCopy', static_id=102, shape_path=[2],
                                        shape_identity='2'*64, signature='3'*64)
    example['success']['data'] = dict(created=True, object=identity,
        actual_bounds_inches=example['success']['data']['actual_bounds_inches'], original_size_points=12.,
        minimum_size_points=8., actual_size_points=12., overflow=False, probe_count=0, probes=[],
        size_tolerance_points=.1, search_scope='largest_verified_probe_under_bounded_overflow_search',
        content_sha256='0'*64, source_preservation={'verified': True,
        'scope': 'root_membership_relative_order_measured_source_text_frame_basic_appearance', 'source_sha256': '1'*64},
        verification_status='implemented_unverified', warnings=['Synthetic schema example; no native/visual acceptance.'])
    registry['tool_examples'][tool['name']] = example
    write('catalog/mcp_tool_registry.json', registry)
    api = read('catalog/coreldraw_x7_api_inventory.json')
    api['evidence_sources'] = [s for s in api['evidence_sources'] if s['id'] != 'x7_text_range_inspection']
    api['evidence_sources'].append({'id': 'x7_text_range_inspection', 'type': 'installed_type_library',
        'path': 'docs/x7_text_range_evidence.json', 'inspection_date': '2026-11-05',
        'description': 'X7 text frame/range/fitting descriptors without application access; SDK responses lacked readable member text.'})
    evidence = read('docs/x7_text_range_evidence.json')
    for member_id in added:
        owner, member_name = member_id.split('.')
        entry = next(m for m in evidence['members'] if m['interface'] == 'IVG' + owner and m['names'][0] == member_name and m['invkind'] == 2)
        if not any(m['id'] == member_id for m in api['members']):
            api['members'].append({'id': member_id, 'owner': owner, 'kind': 'property',
                'access': 'read_write' if member_name in ('VerticalAlignment', 'Fill', 'Outline') else 'read',
                'signature': entry['documentation'], 'status': 'typelib_confirmed', 'used_by': [tool['name']],
                'evidence': ['installed_x7_typelib', 'x7_text_range_inspection'],
                'docs_url': 'https://community.coreldraw.com/sdk/api/draw/17/p/' + member_id.lower(), 'live_test_status': 'not_run'})
    for member in api['members']:
        if member['id'] in tool['api_requirements']:
            member['used_by'] = list(dict.fromkeys(member.get('used_by', []) + [tool['name']]))
    write('catalog/coreldraw_x7_api_inventory.json', api)
    matrix = ROOT / 'catalog/capability_matrix.csv'
    with matrix.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    row = copy.deepcopy(next(r for r in rows if r['tool_name'] == 'set_text_spacing'))
    row.update(capability_id='tool.fit_paragraph_text', tool_name=tool['name'],
        primary_limitation='Bounded independent paragraph copy; glyph/per-run/template and native/manual fitting acceptance remain pending.',
        next_verification='Disposable overflowing/already-fitting/minimum-size copies, source/frame preservation and editable artifact review')
    rows = [r for r in rows if r['tool_name'] != tool['name']] + [row]
    with matrix.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps = read('catalog/workflow_gaps.json')
    gap = next(g for g in gaps['gaps'] if g['id'] == 'typography')
    gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + [tool['name']]))
    gap['implemented_behavior'] = list(dict.fromkeys(gap['implemented_behavior'] + [
        'Source-preserving editable paragraph fitting with explicit minimum size, bounded native overflow probes and guarded cleanup']))
    gap['missing_behavior'] = [s.replace('Safe auto-fit and template reflow',
        'Per-run/artistic/container/linked fitting, safe-area/glyph acceptance and automatic template reflow') for s in gap['missing_behavior']]
    gap['evidence'] = list(dict.fromkeys(gap['evidence'] + tool['test_evidence']['sources']))
    write('catalog/workflow_gaps.json', gaps)
    print('Registered editable paragraph fitting, strict probe contract and installed frame evidence.')


if __name__ == '__main__':
    main()
