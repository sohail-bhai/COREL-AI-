"""Register shared native exclusion inspection and explicit recovery contracts."""
import copy
import csv

from scripts.update_selected_text_catalog import read, write, obj, ROOT


def main():
    registry = read('catalog/mcp_tool_registry.json')
    state = obj({'schema': {'const': 1}, 'phase': {'enum': ['idle', 'running', 'recovery_required']},
                 'operation_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'},
                 'method': {'type': 'string', 'minLength': 1, 'maxLength': 100},
                 'pid': {'type': 'integer', 'minimum': 1}})
    token = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    inspected = obj({'state': {'anyOf': [state, {'type': 'null'}]}, 'fingerprint': token,
                     'recovery_required': {'type': 'boolean'}, 'human_input_locked': {'const': False}})
    reconciled = obj({'reconciled': {'const': True}, 'human_input_locked': {'const': False},
                      'document_state': {'$ref': '#/schema_definitions/reconciled_document_state'}})
    source = next(t for t in registry['tools'] if t['name'] == 'reconcile_operator_state')
    specs = [
        ('get_native_coordination_state', obj({}), inspected, [],
         'Inspect shared native state without waiting for a running COM operation.'),
        ('reconcile_native_coordination', obj({'expected_fingerprint': token,
         'acknowledge_partial_changes': {'type': 'boolean', 'default': False}}, ['expected_fingerprint']),
         reconciled, source['api_requirements'],
         'Recheck a bound document and explicitly acknowledge uncertain shared native state; never undo or replay.')]
    new = []
    for name, inputs, outputs, requirements, description in specs:
        tool = copy.deepcopy(source)
        tool.update(name=name, input_schema=inputs, api_requirements=requirements, description=description,
                    implementation={'state': 'registered', 'server': 'corel_operator/server.py',
                                    'bridge_method': 'CorelBridge.' + name})
        tool['output_schema']['allOf'][1]['then']['properties']['data'] = outputs
        tool['test_evidence'] = {'status': 'mock_com_passed', 'sources': [
            'tests/test_native_coordination.py', 'tests/test_interaction_policy.py', 'docs/CONCURRENT_EDITING.md']}
        tool['known_limitations'] = [
            'Cooperating bridge processes share one per-user native lease. Human CorelDRAW input is not locked.',
            'Live X7 recovery-probe and manual concurrent-document verification remain deferred.',
            'A crash or uncertain write requires explicit shared acknowledgement and separate worker recovery if applicable.',
            'The current bound-document probe cannot prove that all effects in a previous client were reviewed.']
        new.append(tool)
    names = {t['name'] for t in new}
    registry['tools'] = [t for t in registry['tools'] if t['name'] not in names] + new
    sample = copy.deepcopy(registry['tool_examples']['reconcile_operator_state'])
    document = sample['success']['data']['document_state']
    samples = {
        'get_native_coordination_state': ({}, {'state': None, 'fingerprint': 'a' * 64,
            'recovery_required': False, 'human_input_locked': False}),
        'reconcile_native_coordination': ({'expected_fingerprint': 'b' * 64, 'acknowledge_partial_changes': True},
            {'reconciled': True, 'document_state': document, 'human_input_locked': False})}
    for name, (request, data) in samples.items():
        example = copy.deepcopy(sample)
        example['request'] = request
        example['success'].update(tool=name, data=data)
        example['error'].update(tool=name)
        registry['tool_examples'][name] = example
    write('catalog/mcp_tool_registry.json', registry)
    inventory = read('catalog/coreldraw_x7_api_inventory.json')
    for member in inventory['members']:
        if member['id'] in source['api_requirements']:
            member['used_by'] = list(dict.fromkeys(member['used_by'] + ['reconcile_native_coordination']))
    write('catalog/coreldraw_x7_api_inventory.json', inventory)
    path = ROOT / 'catalog/capability_matrix.csv'
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    template = next(row for row in rows if row['tool_name'] == 'reconcile_operator_state')
    rows = [row for row in rows if row['tool_name'] not in names]
    for tool in new:
        row = copy.deepcopy(template)
        row.update(capability_id='tool.' + tool['name'], tool_name=tool['name'], status=tool['status'],
                   primary_limitation=tool['known_limitations'][0],
                   next_verification='Deferred bound-document recovery probe and manual two-document campaign')
        rows.append(row)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)


if __name__ == '__main__':
    main()
