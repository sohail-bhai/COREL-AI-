"""Register repeat inspection, complete sheet plans and owned-output execution."""
import copy
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'tests'))
from scripts.update_raster_catalog import obj, ref, nullable
from corel_operator.print_runs import plan_print_run, UNCHECKED_CHECKS
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.results import success_result, error_result
from print_run_fakes import fixture


def structure(value):
    """Strict keys for the existing bounded layout metadata; values may vary."""
    if type(value) is dict: return obj({k: structure(v) for k, v in value.items()})
    if type(value) is list: return {'type': 'array', 'items': structure(value[0]) if value else {}, 'maxItems': 32}
    if type(value) is bool: return {'type': 'boolean'}
    if type(value) is int: return {'type': 'integer', 'minimum': 0}
    if type(value) is float: return {'type': 'number'}
    if type(value) is str: return {'type': 'string', 'maxLength': 512}
    raise ValueError('Unexpected layout schema value')


def main():
    path = ROOT/'catalog/mcp_tool_registry.json'; registry = json.loads(path.read_text(encoding='utf-8'))
    tools = {tool['name']: tool for tool in registry['tools']}
    definitions = registry['schema_definitions']
    digest = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    positive = {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 200}
    distance = {'type': 'number', 'minimum': 0}
    copies = {'type': 'integer', 'minimum': 1, 'maximum': 500}
    boolean = {'type': 'boolean'}
    warnings = {'type': 'array', 'items': {'type': 'string', 'maxLength': 1000}, 'maxItems': 20}
    unchecked = {'const': UNCHECKED_CHECKS}
    bridge, _, _, _ = fixture(); inspected = bridge.inspect_print_repeat(object_name='Repeat')
    plan = plan_print_run(inspected['repeat'], 5, 6.5, 2.5, gutter_inches=0.)
    executed = bridge.execute_print_run(plan, plan['fingerprint'])
    node = copy.deepcopy(definitions['powerclip_node'])
    for field in ('group_children', 'clip_children'): node['properties'][field]['items'] = ref('print_repeat_node')
    node['properties'].update(effects_count={'const': 0}, gradient=ref('gradient_state'))
    node['required'] += ['effects_count', 'gradient']
    node['properties']['supported_payload'] = {'const': True}
    definitions['print_repeat_node'] = node
    definitions['print_repeat'] = obj({'schema': {'const': 'print-repeat-v1'}, 'object_reference': ref('object_reference'),
        'bounds_inches': ref('bounds_inches'), 'node_count': {'type': 'integer', 'minimum': 1, 'maximum': 1000},
        'segment_count': {'type': 'integer', 'minimum': 0, 'maximum': 10000}, 'tree': ref('print_repeat_node'),
        'verification_scope': {'const': 'measured_native_repeat'}, 'unchecked_checks': unchecked, 'fingerprint': digest})
    request = obj({'repeat': ref('print_repeat'), 'copies': copies, 'sheet_width_inches': positive,
        'sheet_height_inches': positive, 'margin_inches': distance, 'gutter_inches': distance,
        'rotation_policy': {'enum': ['never', 'all', 'best_fit']}, 'sheet_orientation': {'enum': ['fixed', 'portrait', 'landscape', 'best_fit']},
        **{f'margin_{edge}_inches': nullable(distance) for edge in ('left', 'top', 'right', 'bottom')},
        'gripper_inches': distance, 'gripper_edge': {'enum': ['left', 'top', 'right', 'bottom']},
        'mark_clearance_inches': distance, 'object_name_prefix': {'type': 'string', 'minLength': 1, 'maxLength': 100, 'pattern': '^[^\\x00-\\x1f]+$'}})
    definitions['print_run_request'] = request
    definitions['print_run_sheet'] = obj({'page_index': copies, 'first_copy_index': copies, 'last_copy_index': copies,
        'copy_count': copies, 'unused_capacity': {'type': 'integer', 'minimum': 0}, 'partial': boolean,
        'width_inches': positive, 'height_inches': positive})
    placement = structure(plan['placements'][0])
    placement['properties']['rotation_degrees'] = {'enum': [0, 90]}
    definitions['print_run_placement'] = placement
    layout = structure(plan['layout'])
    # The old planner can report that unused capacity exceeded its position cap.
    layout['properties'].update(placements_truncated={'type': 'boolean'}, placements_limit={'type': 'integer', 'minimum': 1})
    definitions['print_run_plan'] = obj({'schema': {'const': 'print-run-plan-v1'}, 'request': ref('print_run_request'),
        'summary': obj({'requested_copies': copies, 'produced_copies': copies, 'overage': {'const': 0},
            'sheet_count': copies, 'capacity_per_sheet': {'type': 'integer', 'minimum': 1},
            'output_shape_count': {'type': 'integer', 'minimum': 1, 'maximum': 50000}}),
        'layout': layout, 'sheets': {'type': 'array', 'items': ref('print_run_sheet'), 'minItems': 1, 'maxItems': 500},
        'placements': {'type': 'array', 'items': ref('print_run_placement'), 'minItems': 1, 'maxItems': 500},
        'scale_percent': {'const': 100.}, 'bleed_inches': {'const': 0.}, 'production_ready': {'const': False},
        'verification_status': {'const': 'implemented_unverified'}, 'warnings': warnings, 'fingerprint': digest})
    inspection = obj({'repeat': ref('print_repeat'), 'verification_status': {'const': 'implemented_unverified'}, 'warnings': warnings})
    execution = obj({'created': {'const': True}, 'copy_count': copies, 'sheet_count': copies,
        'output_shape_count': {'type': 'integer', 'minimum': 1, 'maximum': 50000}, 'approved_fingerprint': digest,
        'output_document': copy.deepcopy(tools['execute_template_batch']['output_schema']['allOf'][1]['then']['properties']['data']['properties']['output_document']),
        'sheets': {'type': 'array', 'items': ref('print_run_sheet'), 'minItems': 1, 'maxItems': 500},
        'items': {'type': 'array', 'items': obj({'copy_index': copies, 'page_index': copies, 'slot_index': copies,
            'object_name': {'type': 'string', 'minLength': 1, 'maxLength': 104}, 'object_reference': nullable(ref('object_reference'))}), 'minItems': 1, 'maxItems': 100},
        'items_truncated': boolean, 'source_preservation': obj({'verified': {'const': True}, 'scope': {'const': 'measured_native_repeat_and_document_context'}}),
        'clipboard_modified': boolean, 'production_ready': {'const': False}, 'verification_status': {'const': 'implemented_unverified'},
        'unchecked_checks': unchecked, 'warnings': warnings})
    inspection_api = sorted(set(sum((tools[name]['api_requirements'] for name in ('get_powerclip', 'get_gradient_fill', 'get_document_structure')), []) + ['Shape.Effects', 'Document.Dirty', 'Document.SelectionRange']))
    execution_api = sorted(set(inspection_api + tools['execute_template_batch']['api_requirements'] + tools['rotate_object']['api_requirements']))
    specs = [
        ('inspect_print_repeat', 'inspect_text_template', 'print_production_inspection', inspection,
            copy.deepcopy(tools['inspect_text_template']['input_schema']), inspection_api, inspected),
        ('plan_print_run', 'plan_template_batch', 'print_production_planning', ref('print_run_plan'), copy.deepcopy(request), [], plan),
        ('execute_print_run', 'execute_template_batch', 'print_production_execution', execution,
            obj({'plan': ref('print_run_plan'), 'approved_fingerprint': digest}), execution_api, executed),
    ]
    for name, base, category, output, inputs, api, example in specs:
        tool = copy.deepcopy(tools[base]); tool.update(name=name, category=category,
            description={'inspect_print_repeat': 'Reconcile two complete native artwork scans and preserved source context.',
                'plan_print_run': 'Plan every full/partial sheet without padded copies, scaling or native calls.',
                'execute_print_run': 'Create independently owned sheets with final payload/placement/count/ownership and source-state checks.'}[name], api_requirements=api)
        tool['implementation']['bridge_method'] = 'CorelBridge.'+name if api else 'corel_operator.print_runs.'+name
        if name == 'plan_print_run':
            inputs['required'] = ['repeat', 'copies', 'sheet_width_inches', 'sheet_height_inches']
            for key in inputs['properties']:
                if key not in inputs['required']: inputs['properties'][key]['default'] = plan['request'][key]
        tool['input_schema'] = inputs; tool['output_schema']['allOf'][1]['then']['properties']['data'] = output
        tool['test_evidence'] = {'status': 'mock_com_passed' if api else 'unit_passed',
            'sources': ['tests/test_print_runs.py', 'tests/integration/test_corel_live.py', 'docs/PRINT_RUNS.md']}
        tool['known_limitations'] = ['Native/manual verification remains deferred; results stay implemented_unverified.',
            '1000 repeat shapes/32 levels/10000 segments/8 MiB; runs limited to 500 copies and 50000 descendant shapes.',
            'Physical size preserved, 0/90-degree rotations; no nonzero bleed, marks, outline-aware trimming or padded copies.',
            'Live effects/opaque containers/complex paint and unlocked PowerClips are refused; pixels, text runs, clipping visuals, color and printer approval remain unchecked.',
            'Inspection requires bounded document structure; native reads cannot provide atomic locking.',
            'Execution replaces the clipboard, binds output on success and closes only an independently owned output on failure.']
        registry['tools'] = [t for t in registry['tools'] if t['name'] != name] + [tool]
        example_request = {'object_name': 'Repeat'} if name == 'inspect_print_repeat' else (
            {'repeat': inspected['repeat'], 'copies': 5, 'sheet_width_inches': 6.5, 'sheet_height_inches': 2.5, 'gutter_inches': 0.} if name == 'plan_print_run' else {'plan': plan, 'approved_fingerprint': plan['fingerprint']})
        registry['tool_examples'][name] = {'request': example_request, 'success': success_result(name, example, 1),
            'error': error_result(name, CorelBridgeError('Print run request was refused.', ErrorCode.INVALID_ARGUMENT), 1)}
    path.write_text(json.dumps(registry, indent=2)+'\n', encoding='utf-8')
    inventory_path = ROOT/'catalog/coreldraw_x7_api_inventory.json'; inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    for member in inventory['members']:
        for name, _, _, _, _, api, _ in specs:
            if member['id'] in api: member['used_by'] = list(dict.fromkeys(member.get('used_by', []) + [name]))
    inventory_path.write_text(json.dumps(inventory, indent=2)+'\n', encoding='utf-8')
    matrix_path = ROOT/'catalog/capability_matrix.csv'
    with matrix_path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = [row for row in reader if row['tool_name'] not in {spec[0] for spec in specs}]
    for name, _, category, _, _, api, _ in specs:
        rows.append(dict(zip(fields, ['tool.'+name, 'approved_atomic', category, name, 'registered', 'implemented_unverified',
            'mutating' if name == 'execute_print_run' else 'read_only', 'P1', 'research_reference', 'confirmed' if api else 'not_applicable',
            'not_run_deferred' if api else 'not_applicable', 'not_required', 'Visual/pixel/glyph/prepress acceptance remains pending.',
            'Deferred synthetic full/partial sheet and rotation gate; independent editable CDR/PDF artifacts.'])))
    with matrix_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps_path = ROOT/'catalog/workflow_gaps.json'; gaps = json.loads(gaps_path.read_text(encoding='utf-8'))
    for gap in gaps['gaps']:
        if gap['id'] in ('print_production', 'export_prepress'):
            gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + [s[0] for s in specs]))
            gap['evidence'] = list(dict.fromkeys(gap.get('evidence', []) + ['docs/PRINT_RUNS.md', 'tests/test_print_runs.py']))
        if gap['id'] == 'print_production':
            gap['implementation_status'] = 'partial_implemented_unverified'
            gap['missing_behavior'] = ['Native/manual acceptance of multisheet and partial-sheet repeat outputs',
                'Nonzero bleed and drawn production marks', 'Broader job-specific native/source/visual production checks']
    gaps_path.write_text(json.dumps(gaps, indent=2)+'\n', encoding='utf-8')
    print('Registered three print run tools with strict repeat/plan/output contracts and existing researched API evidence.')


if __name__ == '__main__': main()
