"""Register selected-text and cooperative editing with strict bounded contracts."""
import copy
import csv
import json
from pathlib import Path

from corel_operator.text_ranges import FORMAT_PROPERTIES
from corel_operator.version import BRIDGE_VERSION, TOOL_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def write(path, value):
    (ROOT / path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def obj(properties, required=None):
    return dict(type='object', properties=properties, additionalProperties=False,
                required=list(properties) if required is None else required)


def nullable(value, default=None):
    return {'anyOf': [value, {'type': 'null'}], 'default': default}


def main():
    registry = read('catalog/mcp_tool_registry.json')
    definitions = registry['schema_definitions']
    template = copy.deepcopy(next(t for t in registry['tools'] if t['name'] == 'set_text_style'))
    local = copy.deepcopy(next(t for t in registry['tools'] if t['name'] == 'get_operator_state'))
    reference = {'$ref': '#/schema_definitions/object_reference'}
    text = {'type': 'string', 'minLength': 1, 'maxLength': 2048}
    offset = {'type': 'integer', 'minimum': 0, 'maximum': 2048}
    fingerprint = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    scope = {'const': 'installed_x7_scalar_character_properties_and_process_appearance'}
    scalar = {'anyOf': [{'type': 'number'}, {'type': 'boolean'}, {'type': 'string', 'maxLength': 200}]}
    native_format = obj({**{attr: scalar for attr in FORMAT_PROPERTIES},
        'fill': {'$ref': '#/schema_definitions/fill_readback'},
        'outline': {'$ref': '#/schema_definitions/outline_readback'},
        'background_fill': {'$ref': '#/schema_definitions/fill_readback'}})
    definitions['range_character_format'] = native_format
    style_fields = {'font': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                    'size_points': {'type': 'number', 'minimum': 1, 'maximum': 500},
                    'bold': {'type': 'boolean'}, 'italic': {'type': 'boolean'},
                    'underline': {'enum': ['none', 'single']}}
    definitions['range_requested_style'] = obj(style_fields, [])
    inspected = obj({'object_reference': reference, 'start': offset, 'end': offset,
        'offset_unit': {'const': 'unicode_code_points'}, 'selected_text': text,
        'story_code_points': {'type': 'integer', 'minimum': 1, 'maximum': 2048},
        'native_character_count': {'type': 'integer', 'minimum': 1, 'maximum': 1024},
        'native_start_index': {'type': 'integer', 'minimum': 1, 'maximum': 1024},
        'native_count': {'type': 'integer', 'minimum': 1, 'maximum': 1024},
        'fingerprint': fingerprint, 'preservation_scope': scope,
        'character_formats': {'type': 'array', 'minItems': 1, 'maxItems': 1024,
            'items': obj({'native_index': {'type': 'integer', 'minimum': 1, 'maximum': 1024},
                          'format': {'$ref': '#/schema_definitions/range_character_format'}})}})
    edited = obj({'updated': {'const': True}, 'object_reference': reference,
        'start': offset, 'end': offset, 'selected_text': text, 'fingerprint': fingerprint,
        'surrounding_text_preserved': {'const': True}, 'surrounding_formatting_preserved': {'const': True},
        'requested_style': {'$ref': '#/schema_definitions/range_requested_style'}, 'preservation_scope': scope})
    policy = obj({'mode': {'enum': ['paused', 'exclusive', 'background_document']},
        'native_writes_paused': {'type': 'boolean'},
        'document_session_id': {'anyOf': [{'type': 'string', 'pattern': '^doc-[0-9]{4,16}$'}, {'type': 'null'}]},
        'background_methods': {'const': ['edit_text_range']}, 'requires_separate_document': {'type': 'boolean'},
        'in_flight_native_call_cancellable': {'const': False}})
    paused = obj({'native_writes_paused': {'const': True}, 'in_flight_native_call_cancellable': {'const': False},
                  'resume_requires_configure_editing_mode': {'const': True}})
    selection = {'allOf': [{'$ref': '#/schema_definitions/reference_object_selector'},
        {'type': 'object', 'properties': {'start': nullable(offset), 'end': nullable(offset)}}],
        'unevaluatedProperties': False}
    edit_input = obj({'object_reference': reference, 'start': offset, 'end': offset,
        'expected_text': text, 'expected_fingerprint': fingerprint, 'replacement': nullable(text),
        **{key: nullable(value) for key, value in style_fields.items()}},
        ['object_reference', 'start', 'end', 'expected_text', 'expected_fingerprint'])
    edit_input['anyOf'] = [{'required': [field], 'properties': {field: {'not': {'type': 'null'}}}}
                           for field in ['replacement', *style_fields]]
    sources = ['tests/test_text_ranges.py', 'tests/test_interaction_policy.py', 'docs/SELECTED_TEXT.md',
               'docs/CONCURRENT_EDITING.md', 'docs/x7_selected_text_evidence.json']
    requirements = ['Shape.GetMatrix', 'Text.Selection', 'TextRange.WideText', 'TextRange.Characters', 'TextCharacters.Item',
                    'TextCharacters.Count', 'TextRange.Start', 'TextRange.End', 'TextRange.Fill', 'TextRange.Outline',
                    'TextRange.CharBackFill', *['TextRange.' + field for field in FORMAT_PROPERTIES]]
    new = []
    specs = [
        ('inspect_text_range', 'Inspect exact Unicode selected content and per-character formatting with a signed target and fingerprint.',
         selection, inspected, 'read_only', requirements),
        ('edit_text_range', 'Edit a fingerprinted text range and verify surrounding text/formatting without automatic undo.',
         edit_input, edited, 'mutating', requirements),
        ('configure_editing_mode', 'Configure paused/exclusive/reserved-background editing; all native server writes start paused.',
         obj({'mode': {'enum': ['paused', 'exclusive', 'background_document']},
              'confirm_exclusive': {'type': 'boolean', 'default': False}}, ['mode']), policy, 'read_only',
         ['Application.ActiveDocument', 'Application.Documents']),
        ('pause_native_editing', 'Immediately pause subsequent native write boundaries without waiting for CorelDRAW.',
         obj({}), paused, 'read_only', []),
    ]
    for name, description, inputs, outputs, permission, api in specs:
        tool = copy.deepcopy(local if name == 'pause_native_editing' else template)
        tool.update(name=name, description=description, permission=permission,
                    category='typography' if 'text_range' in name else 'worker_recovery',
                    input_schema=inputs, api_requirements=sorted(set(api)), confirmation='not_required')
        tool['implementation'] = {'state': 'registered', 'server': 'corel_operator/server.py',
            **({'dispatcher_method': 'pause_native_editing'} if name == 'pause_native_editing' else
               {'bridge_method': 'CorelBridge.' + name})}
        tool['output_schema'] = {'allOf': [{'$ref': '#/schema_definitions/result_envelope'},
            {'if': {'properties': {'ok': {'const': True}}, 'required': ['ok']},
             'then': {'properties': {'data': outputs}}}]}
        tool['test_evidence'] = {'status': 'mock_com_passed', 'sources': sources}
        tool['known_limitations'] = [
            'Live X7 and manual verification remain deferred. Implemented_unverified.',
            'No atomic lock against human input; in-flight COM cannot be cancelled. Use a reserved inactive document for background edits.',
            'Server starts paused. Exclusive mode requires the user to stop editing. Background allows only signed text-range edits.',
            'Text range scope: one unfitted/unlinked story, 1024 native characters; exact scalar/process-appearance preservation.',
            'Unicode code-point offsets with readback-derived native mapping and conservative boundary refusals; shaped-glyph acceptance remains pending.',
            'Replacement requires uniform selected formatting and forbids paragraph breaks/tabs. Uncertain failures require reconciliation, never automatic undo.']
        new.append(tool)
    registry['tools'] = [t for t in registry['tools'] if t['name'] not in {t['name'] for t in new}] + new
    sample_reference = registry['tool_examples']['set_text_style']['success']['data']['object']['object_reference']
    sample_format = {field: 0 for field in FORMAT_PROPERTIES}
    sample_format.update(Font='Arial', Size=12., BulletFont='Arial', BulletSymbol='',
        Bold=False, Italic=False, AutoHyphenate=False, HyphenateCapitals=False, HyphenateAllCapWords=False,
        fill={'type_code': 0, 'type': 'none', 'color': None},
        outline={'type_code': 0, 'type': 'none', 'present': False, 'width_raw': None, 'width_units': None, 'color': None},
        background_fill={'type_code': 0, 'type': 'none', 'color': None})
    sample_scope = scope['const']
    samples = {
        'inspect_text_range': ({'object_name': 'Title', 'start': 0, 'end': 1},
            dict(object_reference=sample_reference, start=0, end=1, offset_unit='unicode_code_points',
                 selected_text='A', story_code_points=1, native_character_count=1, native_start_index=1,
                 native_count=1, fingerprint='a' * 64, character_formats=[{'native_index': 1, 'format': sample_format}],
                 preservation_scope=sample_scope)),
        'edit_text_range': (dict(object_reference=sample_reference, start=0, end=1, expected_text='A',
            expected_fingerprint='a' * 64, bold=True), dict(updated=True, object_reference=sample_reference,
            start=0, end=1, selected_text='A', fingerprint='b' * 64, surrounding_text_preserved=True,
            surrounding_formatting_preserved=True, requested_style={'bold': True}, preservation_scope=sample_scope)),
        'configure_editing_mode': ({'mode': 'paused'}, dict(mode='paused', native_writes_paused=True,
            document_session_id=None, background_methods=['edit_text_range'], requires_separate_document=False,
            in_flight_native_call_cancellable=False)),
        'pause_native_editing': ({}, dict(native_writes_paused=True, in_flight_native_call_cancellable=False,
                                        resume_requires_configure_editing_mode=True)),
    }
    for name, (request, data) in samples.items():
        examples = copy.deepcopy(registry['tool_examples']['get_operator_state'])
        examples['request'] = request
        examples['success'].update(tool=name, data=data)
        examples['error'].update(tool=name)
        registry['tool_examples'][name] = examples
    registry.update(tool_schema_version=TOOL_SCHEMA_VERSION, catalog_revision='2026-11-15')
    definitions['result_envelope']['properties']['bridge_version']['const'] = BRIDGE_VERSION
    definitions['result_envelope']['properties']['tool_schema_version']['const'] = TOOL_SCHEMA_VERSION
    for tool in registry['tools']:
        tool['result_contract'] = f'tool-schema-v{TOOL_SCHEMA_VERSION}-envelope'
    for examples in registry['tool_examples'].values():
        for field in ('success', 'error'):
            examples[field].update(bridge_version=BRIDGE_VERSION, tool_schema_version=TOOL_SCHEMA_VERSION)
    registry['registry_notes'] = list(dict.fromkeys(registry['registry_notes'] + [
        'Tool-schema v2 / bridge 0.7.0: server-native editing now starts paused and requires explicit editing-mode configuration; envelope shape retained.']))
    write('catalog/mcp_tool_registry.json', registry)
    inventory = read('catalog/coreldraw_x7_api_inventory.json')
    source_id = 'x7_selected_text_inspection'
    inventory['evidence_sources'] = [s for s in inventory['evidence_sources'] if s['id'] != source_id] + [
        {'id': source_id, 'type': 'installed_type_library', 'path': 'docs/x7_selected_text_evidence.json',
         'inspection_date': '2026-11-15', 'description': 'Installed indexing/selection descriptors; no CorelDRAW connection. Full scalar descriptors retained in x7_text_range_evidence.json.'}]
    evidence = read('docs/x7_text_range_evidence.json')['members'] + read('docs/x7_selected_text_evidence.json')['members']
    for member_id in sorted(set(requirements)):
        owner, name = member_id.split('.')
        if not any(m['id'] == member_id for m in inventory['members']):
            native = [m for m in evidence if m['interface'] == 'IVG' + owner and m['names'][0] == name]
            if not native: raise ValueError('Missing installed evidence: ' + member_id)
            inventory['members'].append(dict(id=member_id, owner=owner, kind='property',
                access='read_write' if any(m['invkind'] == 4 for m in native) else 'read_only',
                signature=native[0]['descriptor'], status='typelib_confirmed', used_by=[],
                evidence=[source_id], docs_url='https://community.coreldraw.com/sdk/api/draw/17/p/' + member_id.lower(),
                live_test_status='not_run'))
    for member in inventory['members']:
        for tool in new:
            if member['id'] in tool['api_requirements']:
                member['used_by'] = list(dict.fromkeys(member.get('used_by', []) + [tool['name']]))
    write('catalog/coreldraw_x7_api_inventory.json', inventory)
    enums = read('catalog/enum_reference.json')
    enums['enums']['cdrTextIndexingType'] = {
        'values': read('docs/x7_selected_text_evidence.json')['enums']['cdrTextIndexingType'],
        'docs_url': 'https://community.coreldraw.com/sdk/api/draw/17/e/cdrTextIndexingType',
        'bridge_usage': ['Research evidence only; native character mapping is derived per story without changing indexing mode.']}
    write('catalog/enum_reference.json', enums)
    matrix = ROOT / 'catalog/capability_matrix.csv'
    with matrix.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    row_template = next(row for row in rows if row['tool_name'] == 'set_text_style')
    rows = [row for row in rows if row['tool_name'] not in {t['name'] for t in new}]
    for tool in new:
        row = copy.deepcopy(row_template)
        row.update(capability_id='tool.' + tool['name'], tool_name=tool['name'], permission=tool['permission'],
            priority=tool['priority'], status=tool['status'], primary_limitation=tool['known_limitations'][0],
            next_verification='Consolidated disposable selected-text/background interaction campaign and manual artifact review')
        rows.append(row)
    with matrix.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps = read('catalog/workflow_gaps.json')
    gaps['research_date'] = '2026-11-15'
    for gap in gaps['gaps']:
        if gap['id'] not in ('typography', 'recovery'):
            continue
        names = ['inspect_text_range', 'edit_text_range'] if gap['id'] == 'typography' else ['configure_editing_mode', 'pause_native_editing']
        gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + names))
        gap['evidence'] = list(dict.fromkeys(gap.get('evidence', []) + sources))
        behavior = ('Bounded Unicode mapping, signed/fingerprinted selected-range edits and surrounding scalar/process formatting preservation'
                    if gap['id'] == 'typography' else
                    'Paused worker/embedded editing, immediate pause and reserved inactive-document background text edits')
        gap['implemented_behavior'] = list(dict.fromkeys(gap.get('implemented_behavior', []) + [behavior]))
        if gap['id'] == 'typography':
            gap['missing_behavior'] = [s.replace('Per-run and linked/fitted story edits', 'Linked/fitted story edits and broader named-style/glyph preservation')
                                       for s in gap['missing_behavior']]
    write('catalog/workflow_gaps.json', gaps)
    print('Registered four tools, three bounded schemas and installed indexing evidence; tool schema v2.')


if __name__ == '__main__':
    main()
