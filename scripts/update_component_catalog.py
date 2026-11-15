"""Register local component revisions/resizing and an unconnected provider handoff."""
import copy
import csv

from corel_operator.component_designs import UNCHECKED
from corel_operator.design_plans import DESIGN_PLAN_SCHEMA
from scripts.update_selected_text_catalog import read, write, obj, nullable, ROOT


def main():
    registry = read('catalog/mcp_tool_registry.json')
    definitions = registry['schema_definitions']
    definitions['component_plan'] = copy.deepcopy(DESIGN_PLAN_SCHEMA)
    plan = {'$ref': '#/schema_definitions/component_plan'}
    element = copy.deepcopy(DESIGN_PLAN_SCHEMA['properties']['elements']['items'])
    path = {'type': 'string', 'minLength': 1, 'maxLength': 32767}
    fingerprint = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    ids = {'type': 'array', 'maxItems': 200, 'uniqueItems': True,
           'items': {'type': 'string', 'minLength': 1, 'maxLength': 64}}
    base = obj({'path': path, 'fingerprint': fingerprint, 'revision': {'type': 'integer', 'minimum': 0, 'maximum': 63},
        'component_count': {'type': 'integer', 'minimum': 1, 'maximum': 200}, 'plan': plan,
        'changed_component_ids': ids, 'history_count': {'type': 'integer', 'minimum': 1, 'maximum': 64},
        'verification_status': {'const': 'implemented_unverified'}, 'unchecked_checks': {'const': UNCHECKED}})
    definitions['component_result'] = base
    history_entry = obj({'revision': {'type': 'integer', 'minimum': 0, 'maximum': 63},
        'action': {'enum': ['create', 'replace', 'restore', 'resize']}, 'fingerprint': fingerprint,
        'changed_component_ids': ids})
    inspected = copy.deepcopy(base)
    inspected['properties']['history'] = {'type': 'array', 'minItems': 1, 'maxItems': 64, 'items': history_entry}
    inspected['required'].append('history')
    resized = copy.deepcopy(base)
    resized['properties'].update(scale_factor={'type': 'number', 'exclusiveMinimum': 0},
        requires_higher_resolution_components=ids, minimum_image_dpi={'type': 'number', 'minimum': 1, 'maximum': 2400},
        minimum_font_size_points={'type': 'number', 'minimum': 1, 'maximum': 500})
    resized['required'] = list(resized['properties'])
    request = obj({'schema': {'const': 'component-generation-request-v1'},
        'provider': {'const': 'local_asset_handoff'}, 'design_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'},
        'source_design_fingerprint': fingerprint, 'component_id': {'type': 'string', 'minLength': 1, 'maxLength': 64},
        'current_component': element, 'prompt': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
        'width_pixels': {'type': 'integer', 'minimum': 1, 'maximum': 16384},
        'height_pixels': {'type': 'integer', 'minimum': 1, 'maximum': 16384},
        'provider_connected': {'const': False}, 'generated': {'const': False},
        'network_request_sent': {'const': False}, 'fingerprint': fingerprint})
    definitions['component_generation_request'] = request
    generated = obj({'path': path, 'request': {'$ref': '#/schema_definitions/component_generation_request'},
        'fingerprint': fingerprint, 'provider_connected': {'const': False}, 'generated': {'const': False},
        'network_request_sent': {'const': False}, 'verification_status': {'const': 'implemented_unverified'}})
    source = {'source_path': path, 'destination_path': path, 'expected_fingerprint': fingerprint}
    revise = obj({**source, 'component_id': nullable({'type': 'string', 'minLength': 1, 'maxLength': 64}),
        'replacement_element': nullable(element), 'restore_revision': nullable({'type': 'integer', 'minimum': 0, 'maximum': 63})}, list(source))
    revise['oneOf'] = [
        {'required': ['component_id', 'replacement_element'], 'properties': {
            'component_id': {'not': {'type': 'null'}}, 'replacement_element': {'not': {'type': 'null'}},
            'restore_revision': {'type': 'null'}}},
        {'required': ['restore_revision'], 'properties': {'restore_revision': {'not': {'type': 'null'}},
            'component_id': {'type': 'null'}, 'replacement_element': {'type': 'null'}}}]
    resize = obj({**source, 'width_inches': {'type': 'number', 'minimum': .001, 'maximum': 200},
        'height_inches': {'type': 'number', 'minimum': .001, 'maximum': 200},
        'minimum_font_size_points': {'type': 'number', 'minimum': 1, 'maximum': 500, 'default': 8.},
        'minimum_image_dpi': {'type': 'number', 'minimum': 1, 'maximum': 2400, 'default': 300.}},
        [*source, 'width_inches', 'height_inches'])
    prepare = obj({'source_path': path, 'destination_path': path, 'component_id': {'type': 'string', 'minLength': 1, 'maxLength': 64},
        'expected_fingerprint': fingerprint, 'prompt': {'type': 'string', 'minLength': 1, 'maxLength': 4000},
        'width_pixels': {'type': 'integer', 'minimum': 1, 'maximum': 16384, 'default': 1024},
        'height_pixels': {'type': 'integer', 'minimum': 1, 'maximum': 16384, 'default': 1024}},
        ['source_path', 'destination_path', 'component_id', 'expected_fingerprint', 'prompt'])
    template = next(t for t in registry['tools'] if t['name'] == 'inspect_raster_asset')
    specs = [
        ('create_component_design', obj({'plan': plan, 'destination_path': path}), base, 'external_io',
         'Create an immutable local editable component plan with raster receipts and a revision chain.'),
        ('inspect_component_design', obj({'path': path}), inspected, 'read_only',
         'Inspect a local component design, current asset receipts and verified bounded revision history.'),
        ('revise_component_design', revise, base, 'external_io',
         'Replace one component or restore a prior revision into a new file; preserve source and other components.'),
        ('resize_component_design', resize, resized, 'external_io',
         'Proportionally fit/center a draft with minimum font size and selective low-resolution raster flags.'),
        ('prepare_component_generation', prepare, generated, 'external_io',
         'Prepare an unconnected local provider-handoff request; no image generation or network request occurs.'),
    ]
    sources = ['tests/test_component_designs.py', 'docs/COMPONENT_DESIGNS.md',
               'docs/test-reports/2026-11-15-component-designs-non-live.md']
    tools = []
    for name, inputs, outputs, permission, description in specs:
        tool = copy.deepcopy(template)
        tool.update(name=name, category='component_designs', input_schema=inputs, permission=permission, description=description)
        tool['implementation']['bridge_method'] = 'corel_operator.component_designs.' + name
        tool['output_schema'] = {'allOf': [{'$ref': '#/schema_definitions/result_envelope'},
            {'if': {'properties': {'ok': {'const': True}}, 'required': ['ok']}, 'then': {'properties': {'data': outputs}}}]}
        tool['test_evidence'] = {'status': 'offline_passed', 'sources': sources}
        tool['known_limitations'] = [
            'Local draft/revision/request files only; no CorelDRAW or generation-service access, no native application rollback.',
            'Stable component IDs preserve other plan elements; raster byte/pixel receipts do not prove native rendering or print acceptance.',
            'Generation provider remains unconnected. Requests explicitly report generated=false and network_request_sent=false.',
            'Resize is proportional fitting/centering; text fit, glyphs, responsive layout reflow, bleed and color acceptance remain unchecked.',
            'History is bounded to 64 revisions/5 MiB. Current/historical changed assets refuse applicable use/restore. No overwrite.',
            'Atomic non-overwrite hard-link publication requires a supporting local filesystem; uncertain concurrent outputs are preserved.']
        tools.append(tool)
    registry['tools'] = [t for t in registry['tools'] if t['name'] not in {t['name'] for t in tools}] + tools
    sample_plan = {'version': '1.0', 'name': 'Card', 'canvas': {'width_inches': 4., 'height_inches': 2.},
        'elements': [{'id': 'name', 'type': 'text', 'x_inches': 1., 'y_inches': 1., 'text': 'First', 'font_size_points': 24.}]}
    sample_base = dict(path='C:/Projects/Card/design-0.json', fingerprint='a' * 64, revision=0,
        component_count=1, plan=sample_plan, changed_component_ids=['name'], history_count=1,
        verification_status='implemented_unverified', unchecked_checks=UNCHECKED)
    sample_request = dict(schema='component-generation-request-v1', provider='local_asset_handoff',
        design_id='a' * 32, source_design_fingerprint='a' * 64, component_id='name',
        current_component=sample_plan['elements'][0], prompt='A portrait for this component', width_pixels=1024,
        height_pixels=1024, provider_connected=False, generated=False, network_request_sent=False, fingerprint='b' * 64)
    examples = {
        'create_component_design': ({'plan': sample_plan, 'destination_path': sample_base['path']}, sample_base),
        'inspect_component_design': ({'path': sample_base['path']}, dict(sample_base,
            history=[dict(revision=0, action='create', fingerprint='b' * 64, changed_component_ids=['name'])])),
        'revise_component_design': (dict(source_path=sample_base['path'], destination_path='C:/Projects/Card/design-1.json',
            expected_fingerprint='a' * 64, component_id='name', replacement_element=dict(sample_plan['elements'][0], text='Second')),
            dict(sample_base, path='C:/Projects/Card/design-1.json', revision=1, history_count=2,
                 plan=dict(sample_plan, elements=[dict(sample_plan['elements'][0], text='Second')]))),
        'resize_component_design': (dict(source_path=sample_base['path'], destination_path='C:/Projects/Card/design-large.json',
            expected_fingerprint='a' * 64, width_inches=8., height_inches=4.), dict(sample_base, revision=1, history_count=2,
            path='C:/Projects/Card/design-large.json', scale_factor=2., minimum_image_dpi=300., minimum_font_size_points=8.,
            requires_higher_resolution_components=[], plan=dict(sample_plan, canvas={'width_inches': 8., 'height_inches': 4.},
                elements=[dict(sample_plan['elements'][0], x_inches=2., y_inches=2., font_size_points=48.)]))),
        'prepare_component_generation': (dict(source_path=sample_base['path'], destination_path='C:/Projects/Card/request.json',
            expected_fingerprint='a' * 64, component_id='name', prompt=sample_request['prompt']),
            dict(path='C:/Projects/Card/request.json', request=sample_request, fingerprint='b' * 64,
                 provider_connected=False, generated=False, network_request_sent=False, verification_status='implemented_unverified')),
    }
    for name, (inputs, output) in examples.items():
        example = copy.deepcopy(registry['tool_examples']['inspect_raster_asset'])
        example['request'] = inputs
        example['success'].update(tool=name, data=output)
        example['error']['tool'] = name
        registry['tool_examples'][name] = example
    note = 'Local component design revisions/resizing and provider handoff are drafts only; no connected generation service or native component replacement is claimed.'
    registry['registry_notes'] = list(dict.fromkeys(registry['registry_notes'] + [note]))
    write('catalog/mcp_tool_registry.json', registry)
    matrix = ROOT / 'catalog/capability_matrix.csv'
    with matrix.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    template_row = next(row for row in rows if row['tool_name'] == 'inspect_raster_asset')
    rows = [row for row in rows if row['tool_name'] not in {t['name'] for t in tools}]
    for tool in tools:
        row = copy.deepcopy(template_row)
        row.update(capability_id='tool.' + tool['name'], tool_name=tool['name'], permission=tool['permission'],
            priority=tool['priority'], status=tool['status'], primary_limitation=tool['known_limitations'][0],
            next_verification='Consolidated MCP envelope checks; native component composition and visual review remain separate.')
        rows.append(row)
    with matrix.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps = read('catalog/workflow_gaps.json')
    for gap in gaps['gaps']:
        if gap['id'] not in ('ai_components', 'redesign_history'):
            continue
        gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + [t['name'] for t in tools]))
        gap['implemented_behavior'] = list(dict.fromkeys(gap.get('implemented_behavior', []) + [
            'Local stable-ID editable/raster/primitive component plans, guarded single-component revisions and historical restore to new files',
            'Proportional draft resize with readable-font refusal and selective low-resolution raster flags',
            'Local provider-handoff requests with explicit unconnected/not-generated state']))
        gap['evidence'] = list(dict.fromkeys(gap.get('evidence', []) + sources))
        gap.update(coverage='partial', implementation_status='partial_implemented_unverified')
        if gap['id'] == 'ai_components':
            gap['missing_behavior'] = ['Connected approved image provider and actual generation',
                'Native independent component assembly/replacement with source preservation', 'General vector-component payload inspection']
        else:
            gap['missing_behavior'] = ['Responsive native layout reflow and text fitting', 'Selective sufficient-resolution regeneration',
                'Native revision diff and verified CDR restoration']
    write('catalog/workflow_gaps.json', gaps)
    print('Registered five local component tools, three bounded definitions and explicit provider limits.')


if __name__ == '__main__':
    main()
