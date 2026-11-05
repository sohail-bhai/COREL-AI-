"""Register researched X7 leading/paragraph spacing and strict contracts."""
import copy
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNITS = ['percent_character_height', 'points', 'percent_point_size']
FIELDS = ['line_spacing', 'paragraph_before', 'paragraph_after']


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def write(path, data):
    (ROOT / path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def main():
    registry = read('catalog/mcp_tool_registry.json')
    tool = copy.deepcopy(next(t for t in registry['tools'] if t['name'] == 'set_text_style'))
    tool['name'] = 'set_text_spacing'
    tool['description'] = 'Set whole-story line and paragraph spacing in documented X7 units; preserve content and verify native readback.'
    tool['implementation']['bridge_method'] = 'CorelBridge.set_text_spacing'
    numbers = {field: {'type': 'number', 'minimum': .01 if field == 'line_spacing' else 0, 'maximum': 2000}
               for field in FIELDS}
    requested = obj(numbers, [])
    requested['minProperties'] = 1
    registry['schema_definitions']['requested_text_spacing'] = requested
    registry['schema_definitions']['actual_text_spacing'] = obj({
        **{field: {'type': 'number', 'minimum': 0} for field in FIELDS},
        'spacing_unit': {'enum': UNITS}, 'spacing_type_code': {'enum': [0, 1, 2]}})
    properties = {field: {'anyOf': [schema, {'type': 'null'}], 'default': None}
                  for field, schema in numbers.items()}
    properties['spacing_unit'] = {'enum': UNITS, 'default': UNITS[0]}
    tool['input_schema'] = {'allOf': [
        {'$ref': '#/schema_definitions/reference_object_selector'},
        {'type': 'object', 'properties': properties,
         'anyOf': [{'required': [field], 'properties': {field: {'not': {'type': 'null'}}}} for field in FIELDS]}],
        'unevaluatedProperties': False}
    data = tool['output_schema']['allOf'][1]['then']['properties']['data']
    for key in ['before_style', 'requested_style', 'actual_style']:
        del data['properties'][key]
    data['properties'].update({
        'before_spacing': {'$ref': '#/schema_definitions/actual_text_spacing'},
        'requested_spacing': {'$ref': '#/schema_definitions/requested_text_spacing'},
        'actual_spacing': {'$ref': '#/schema_definitions/actual_text_spacing'},
        'content_preserved': {'const': True}})
    data['required'] = list(data['properties'])
    tool['api_requirements'] = [x for x in tool['api_requirements']
                                if x not in ['Application.FontList', 'FontList.Count', 'FontList.Item']]
    added = ['TextRange.SetLineSpacing', 'TextRange.ParaSpacingBefore', 'TextRange.ParaSpacingAfter']
    tool['api_requirements'] = sorted(set(tool['api_requirements'] + added))
    tool['test_evidence']['sources'] = ['tests/test_text_spacing.py', 'docs/TEXT_SPACING.md', 'docs/x7_text_spacing_evidence.json']
    tool['known_limitations'] = [
        'Native/visual verification remains deferred to the consolidated campaign.',
        'One unfitted unlinked frame; mixed or unreadable existing spacing is refused.',
        'Unit changes require all three explicit values; aggregate style preservation cannot prove per-run fidelity.',
        'Character/word spacing units, glyph coverage and auto-fit remain separate gaps.',
        'Failures after a native call require exact operation reconciliation; no automatic replay or rollback.']
    registry['tools'] = [t for t in registry['tools'] if t['name'] != tool['name']] + [tool]
    examples = copy.deepcopy(registry['tool_examples']['set_text_style'])
    examples['request'] = {'line_spacing': 125, 'object_name': 'Title'}
    examples['success']['tool'] = examples['error']['tool'] = tool['name']
    example_data = examples['success']['data']
    for key in ['before_style', 'requested_style', 'actual_style']:
        del example_data[key]
    before = dict(line_spacing=100., paragraph_before=4., paragraph_after=6.,
                  spacing_type_code=0, spacing_unit=UNITS[0])
    example_data.update(before_spacing=before, actual_spacing=dict(before, line_spacing=125.),
                        requested_spacing={'line_spacing': 125.}, content_preserved=True)
    example_data['layout']['line_spacing_native'] = 125.
    registry['tool_examples'][tool['name']] = examples
    write('catalog/mcp_tool_registry.json', registry)
    api = read('catalog/coreldraw_x7_api_inventory.json')
    api['evidence_sources'] = [s for s in api['evidence_sources'] if s['id'] != 'x7_text_spacing_inspection']
    api['evidence_sources'].append({'id': 'x7_text_spacing_inspection', 'type': 'installed_type_library',
        'path': 'docs/x7_text_spacing_evidence.json', 'inspection_date': '2026-11-05',
        'description': 'Installed X7 spacing get/let/method descriptors and cdrLineSpacingType; no application connection.'})
    signatures = {'TextRange.SetLineSpacing': 'SetLineSpacing(Type cdrLineSpacingType, LineSpacing Single=-1, ParaBefore Single=-1, ParaAfter Single=-1)',
                  'TextRange.ParaSpacingBefore': 'ParaSpacingBefore get/let Single',
                  'TextRange.ParaSpacingAfter': 'ParaSpacingAfter get/let Single'}
    for member_id, signature in signatures.items():
        api['members'] = [m for m in api['members'] if m['id'] != member_id]
        api['members'].append({'id': member_id, 'owner': 'TextRange', 'kind': 'method' if member_id.endswith('SetLineSpacing') else 'property',
            'access': 'call' if member_id.endswith('SetLineSpacing') else 'read_write', 'signature': signature,
            'status': 'typelib_confirmed', 'used_by': [tool['name']],
            'evidence': ['installed_x7_typelib', 'x7_text_spacing_inspection'],
            'docs_url': 'https://community.coreldraw.com/sdk/api/draw/17/' + ('m/' if member_id.endswith('SetLineSpacing') else 'p/') + member_id.lower(),
            'live_test_status': 'not_run'})
    for member in api['members']:
        if member['id'] in tool['api_requirements']:
            member['used_by'] = list(dict.fromkeys(member.get('used_by', []) + [tool['name']]))
    write('catalog/coreldraw_x7_api_inventory.json', api)
    enums = read('catalog/enum_reference.json')
    native_evidence = read('docs/x7_text_spacing_evidence.json')
    enums['enums']['cdrLineSpacingType'] = {
        'docs_url': 'https://community.coreldraw.com/sdk/api/draw/17/e/cdrLineSpacingType',
        'values': native_evidence['enums']['cdrLineSpacingType'],
        'bridge_usage': ['set_text_spacing explicit native unit dispatch; mixed code 3 refused'],
        'notes': ['Installed X7 enum evidence in docs/x7_text_spacing_evidence.json.']}
    write('catalog/enum_reference.json', enums)
    matrix = ROOT / 'catalog/capability_matrix.csv'
    with matrix.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    row = copy.deepcopy(next(r for r in rows if r['tool_name'] == 'set_text_style'))
    row.update(capability_id='tool.set_text_spacing', tool_name=tool['name'],
               primary_limitation='Single frame whole-story leading/paragraph edits; native/visual and per-run fidelity pending.',
               next_verification='Disposable point/percentage edits, preservation, overflow and editable artifact review')
    rows = [r for r in rows if r['tool_name'] != tool['name']] + [row]
    with matrix.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps = read('catalog/workflow_gaps.json')
    gap = next(g for g in gaps['gaps'] if g['id'] == 'typography')
    gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + [tool['name']]))
    gap['missing_behavior'] = [s.replace('Spacing writes with established user-facing units',
                                        'Character/word spacing writes with established user-facing units') for s in gap['missing_behavior']]
    gap['implemented_behavior'] = list(dict.fromkeys(gap['implemented_behavior'] + [
        'Guarded whole-story leading/paragraph spacing in documented X7 points and percentage units']))
    gap['evidence'] = list(dict.fromkeys(gap['evidence'] + tool['test_evidence']['sources']))
    write('catalog/workflow_gaps.json', gaps)
    print('Registered researched X7 text spacing, two strict definitions and three native members.')


if __name__ == '__main__':
    main()
