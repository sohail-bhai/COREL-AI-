"""Register the installed X7 whole-frame horizontal-spacing structure path."""
import copy
import csv

from update_text_spacing_catalog import ROOT, obj, read, write

NAME = 'set_text_horizontal_spacing'
FIELDS = ('character_spacing_percent', 'word_spacing_percent')


def main():
    registry = read('catalog/mcp_tool_registry.json')
    tool = copy.deepcopy(next(t for t in registry['tools'] if t['name'] == 'set_text_spacing'))
    tool.update(name=NAME, description='Set whole-story character/word spacing as percentages of the space character through an explicit X7 spacing structure; preserve leading and content.')
    tool['implementation']['bridge_method'] = 'CorelBridge.' + NAME
    tool['introduced'] = {'bridge_version': '0.7.0', 'tool_schema_version': 2}
    numbers = {field: {'type': 'number', 'minimum': -100 if field == FIELDS[0] else 0, 'maximum': 2000}
               for field in FIELDS}
    requested = obj(numbers, [])
    requested['minProperties'] = 1
    registry['schema_definitions']['requested_horizontal_spacing'] = requested
    registry['schema_definitions']['actual_horizontal_spacing'] = obj({**numbers,
        'line_spacing': {'type': 'number', 'exclusiveMinimum': 0},
        'spacing_type_code': {'enum': [0, 1, 2]},
        'paragraph_before': {'type': 'number', 'minimum': 0},
        'paragraph_after': {'type': 'number', 'minimum': 0}})
    tool['input_schema'] = {'allOf': [
        {'$ref': '#/schema_definitions/reference_object_selector'},
        {'type': 'object', 'properties': {field: {'anyOf': [schema, {'type': 'null'}], 'default': None}
                                         for field, schema in numbers.items()},
         'anyOf': [{'required': [field], 'properties': {field: {'not': {'type': 'null'}}}} for field in FIELDS]}],
        'unevaluatedProperties': False}
    data = tool['output_schema']['allOf'][1]['then']['properties']['data']
    data['properties'].update({
        'spacing_unit': {'const': 'percent_space_character'},
        'before_spacing': {'$ref': '#/schema_definitions/actual_horizontal_spacing'},
        'actual_spacing': {'$ref': '#/schema_definitions/actual_horizontal_spacing'},
        'requested_spacing': {'$ref': '#/schema_definitions/requested_horizontal_spacing'}})
    data['required'] = list(data['properties'])
    added = {
        'Application.CreateStructSpaceProperties': ('method', 'call', 'CreateStructSpaceProperties() -> StructSpaceProperties'),
        'Text.SpaceProperties': ('property', 'read_write', 'SpaceProperties(Frames cdrTextFrames=2) get/let StructSpaceProperties; Python GetSpaceProperties/SetSpaceProperties'),
        'Text.AlignProperties': ('property', 'read', 'AlignProperties(Frames cdrTextFrames=2) get StructAlignProperties; Python GetAlignProperties'),
        **{'StructSpaceProperties.' + attr: ('property', 'read_write', attr + ' get/let ' +
                ('cdrLineSpacingType' if attr == 'LineSpacingType' else 'Single'))
           for attr in ('CharacterSpacing', 'WordSpacing', 'LineSpacing', 'LineSpacingType', 'BeforeParagraphSpacing', 'AfterParagraphSpacing')},
        **{'StructAlignProperties.' + attr: ('property', 'read', attr + ' get Single')
           for attr in ('MaxCharacterSpacing', 'MinWordSpacing', 'MaxWordSpacing')},
    }
    frame_members = {'Text.Frame', 'TextFrame.FrameShape', 'TextFrame.IsInsideContainer', 'TextFrame.IsFittedToPath',
                     'TextFrame.ColumnCount', 'TextFrame.VerticalAlignment', 'TextFrame.ColumnWidth', 'TextFrame.ColumnGutter'}
    tool['api_requirements'] = sorted((set(tool['api_requirements']) - {'TextRange.SetLineSpacing'}) | set(added) | frame_members)
    tool['test_evidence']['sources'] = ['tests/test_horizontal_spacing.py', 'docs/TEXT_SPACING.md',
        'docs/x7_horizontal_spacing_evidence.json', 'docs/test-reports/2026-11-15-horizontal-spacing-non-live.md']
    tool['known_limitations'] = [
        'Native units and visual acceptance remain deferred; X7 word units combine installed descriptors with X7 user-guide UI evidence, and X7.4 API remarks are supplementary.',
        'One unfitted unlinked whole story with readable uniform basic formatting; paragraph container/path fitting is refused and at most 20 columns are preserved; native justification limits are retained.',
        'Aggregate basic-style preservation cannot prove per-run, glyph, appearance or artistic-anchor fidelity.',
        'Fresh explicit structure only; no indexed character-range edits, scalar spacing setters, auto-fit or document save.',
        'Failures after native application require operation reconciliation; no automatic replay or rollback.']
    registry['tools'] = [t for t in registry['tools'] if t['name'] != NAME] + [tool]
    leading_tool = next(t for t in registry['tools'] if t['name'] == 'set_text_spacing')
    leading_tool['known_limitations'] = [s.replace(
        'Character/word spacing units, glyph coverage and auto-fit remain separate gaps.',
        'Whole-story character/word spacing uses set_text_horizontal_spacing; per-run spacing, glyph coverage and auto-fit remain gaps.')
        for s in leading_tool['known_limitations']]
    examples = copy.deepcopy(registry['tool_examples']['set_text_spacing'])
    examples['request'] = {'character_spacing_percent': 10, 'word_spacing_percent': 110, 'object_name': 'Title'}
    examples['success']['tool'] = examples['error']['tool'] = NAME
    example_data = examples['success']['data']
    before = dict(character_spacing_percent=0., word_spacing_percent=100., line_spacing=100.,
                  spacing_type_code=0, paragraph_before=4., paragraph_after=6.)
    example_data.update(spacing_unit='percent_space_character', before_spacing=before,
        actual_spacing=dict(before, character_spacing_percent=10., word_spacing_percent=110.),
        requested_spacing={FIELDS[0]: 10., FIELDS[1]: 110.})
    example_data['layout'].update(char_spacing_native=10., word_spacing_native=110., line_spacing_native=100.)
    registry['tool_examples'][NAME] = examples
    write('catalog/mcp_tool_registry.json', registry)

    api = read('catalog/coreldraw_x7_api_inventory.json')
    evidence_id = 'x7_horizontal_spacing_inspection'
    api['evidence_sources'] = [s for s in api['evidence_sources'] if s['id'] != evidence_id] + [{
        'id': evidence_id, 'type': 'installed_type_library', 'path': 'docs/x7_horizontal_spacing_evidence.json',
        'inspection_date': '2026-11-15', 'description': 'Installed X7 spacing/alignment structures, frame enums and generated indexed-property Python bindings; no application connection.'}]
    for member_id, (kind, access, signature) in added.items():
        existing = next((m for m in api['members'] if m['id'] == member_id), None)
        if existing is None:
            existing = {'id': member_id, 'owner': member_id.split('.')[0], 'kind': kind, 'access': access,
                'signature': signature, 'status': 'typelib_confirmed', 'used_by': [],
                'evidence': ['installed_x7_typelib', evidence_id],
                'docs_url': 'https://community.coreldraw.com/sdk/api/draw/17/' + ('m/' if kind == 'method' else 'p/') + member_id.lower(),
                'live_test_status': 'not_run'}
            api['members'].append(existing)
    for member in api['members']:
        if member['id'] in tool['api_requirements']:
            member['used_by'] = list(dict.fromkeys(member.get('used_by', []) + [NAME]))
    write('catalog/coreldraw_x7_api_inventory.json', api)
    enums = read('catalog/enum_reference.json')
    enums['enums']['cdrTextFrames'] = {
        'docs_url': 'https://community.coreldraw.com/sdk/api/draw/17/e/cdrTextFrames',
        'values': read('docs/x7_horizontal_spacing_evidence.json')['enums']['cdrTextFrames'],
        'bridge_usage': [NAME + ' explicitly supplies cdrAllFrames=2 to structure getter/setter'],
        'notes': ['Installed enum descriptors; no range start-index assumptions.']}
    write('catalog/enum_reference.json', enums)
    matrix = ROOT / 'catalog/capability_matrix.csv'
    with matrix.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    row = copy.deepcopy(next(r for r in rows if r['tool_name'] == 'set_text_spacing'))
    row.update(capability_id='tool.' + NAME, tool_name=NAME,
        primary_limitation='Whole-story horizontal percentages; native unit, glyph and per-run/visual acceptance pending.',
        next_verification='Disposable artistic/paragraph spacing, native limits, leading/frame/content preservation and editable CDR review')
    rows = [r for r in rows if r['tool_name'] != NAME] + [row]
    with matrix.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps = read('catalog/workflow_gaps.json')
    gap = next(g for g in gaps['gaps'] if g['id'] == 'typography')
    gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + [NAME]))
    gap['missing_behavior'] = [s.replace('Character/word spacing writes with established user-facing units',
        'Per-run horizontal spacing and native/visual acceptance of whole-story space-character percentages') for s in gap['missing_behavior']]
    gap['implemented_behavior'] = list(dict.fromkeys(gap['implemented_behavior'] + [
        'Whole-story character/word spacing via fresh X7 structures, existing justification bounds, content/leading preservation and scalar/structure readback']))
    gap['evidence'] = list(dict.fromkeys(gap['evidence'] + tool['test_evidence']['sources']))
    write('catalog/workflow_gaps.json', gaps)
    print('Registered whole-frame horizontal spacing with 12 native members and cdrTextFrames evidence.')


if __name__ == '__main__':
    main()
