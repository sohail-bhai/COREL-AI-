"""Register strict PDF prepress contracts and researched X7 bleed controls."""
import copy
import csv
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pypdf import PdfWriter
from corel_operator.pdf_inspection import inspect_pdf
from corel_operator.pdf_prepress import preflight_pdf
from corel_operator.results import success_result, error_result
from corel_operator.errors import CorelBridgeError, ErrorCode


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required,
            'additionalProperties': False}


def nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


def ref(name):
    return {'$ref': '#/schema_definitions/' + name}


def array(schema, maximum=100):
    return {'type': 'array', 'items': schema, 'maxItems': maximum}


def main():
    registry_path = ROOT / 'catalog/mcp_tool_registry.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    registry['catalog_revision'] = '2026-11-05'
    boolean = {'type': 'boolean'}
    number = {'type': 'number'}
    integer = {'type': 'integer', 'minimum': 0, 'maximum': 10000}
    string = {'type': 'string', 'maxLength': 1000}
    digest = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    local_path = {'type': 'string', 'minLength': 1, 'maxLength': 32767}
    size = obj({key: {'type': 'number', 'minimum': .001, 'maximum': 200} for key in ('width', 'height')})
    check = nullable(boolean)
    definitions = {
        'pdf_prepress_page': obj({'page_index': {'type': 'integer', 'minimum': 1, 'maximum': 500},
            'box_relationships_passed': boolean, 'trim_size_matches': check,
            'bleed_margins_inches': nullable(obj({edge: number for edge in ('left', 'bottom', 'right', 'top')})), 'bleed_matches': check}),
        'pdf_prepress_image': obj({'width_pixels': {'type': 'integer', 'minimum': 1, 'maximum': 1000000},
            'height_pixels': {'type': 'integer', 'minimum': 1, 'maximum': 1000000}, 'image_mask': boolean}),
        'pdf_prepress_graphics_state': obj({'stroke_overprint': boolean, 'fill_overprint': boolean,
            'overprint_mode': {'enum': [0, 1]}}),
        'pdf_prepress_intent': obj({'subtype': string, 'identifier': string, 'embedded_profile_present': boolean,
            'encoded_profile_bytes': {'type': 'integer', 'minimum': 0, 'maximum': 52428800}, 'encoded_profile_sha256': nullable(digest)}),
        'pdf_prepress_inventory': obj({'color_space_families': array(string, 32), 'spot_colorant_count': integer,
            'spot_colorants': array(string), 'spot_colorants_truncated': boolean, 'image_resource_count': integer,
            'images': array(ref('pdf_prepress_image')), 'images_truncated': boolean, 'graphics_state_count': integer,
            'overprint_enabled_state_count': integer, 'graphics_states': array(ref('pdf_prepress_graphics_state')),
            'graphics_states_truncated': boolean, 'visits': integer, 'complete_for_supported_resources': boolean,
            'unsupported_reasons': array(string, 20)}),
        'pdf_prepress': obj({'path': local_path, 'bytes': {'type': 'integer', 'minimum': 1, 'maximum': 52428800},
            'source_sha256': digest, 'page_count': {'type': 'integer', 'minimum': 1, 'maximum': 500},
            'pages': array(ref('pdf_prepress_page')), 'pages_truncated': boolean,
            'checks': obj({key: boolean if key == 'box_relationships_passed' else check for key in
                ('box_relationships_passed', 'trim_sizes_match', 'bleed_margins_match', 'embedded_fonts_passed', 'output_intent_present')}),
            'checks_passed': boolean, 'resource_inventory': ref('pdf_prepress_inventory'),
            'output_intents': array(ref('pdf_prepress_intent'), 32),
            'pdfx_declarations': obj({key: nullable(string) for key in ('GTS_PDFXVersion', 'GTS_PDFXConformance')}),
            'font_resource_count': integer, 'unembedded_font_count': integer, 'verification_status': {'const': 'implemented_unverified'},
            'production_ready': {'const': False}, 'warnings': array(string, 20)}),
    }
    registry['schema_definitions'].update(definitions)
    export = next(t for t in registry['tools'] if t['name'] == 'export_pdf_controlled')
    export['description'] = 'Export all pages with researched bleed/mark/overprint controls, measured boxes, restored settings and exclusive publication.'
    export['input_schema']['properties'].update(bleed_inches={'type': 'number', 'minimum': 0, 'maximum': 1, 'default': 0},
        crop_marks={**boolean, 'default': False}, registration_marks={**boolean, 'default': False}, preserve_overprints={**boolean, 'default': True})
    output = export['output_schema']['allOf'][1]['then']['properties']['data']
    controls = output['properties']['controls']
    controls['properties'].update(bleed_inches={'type': 'number', 'minimum': 0, 'maximum': 1}, marks_enabled=boolean,
        requested_bleed_inches={'type': 'number', 'minimum': 0, 'maximum': 1}, native_bleed_units={'type': 'integer', 'minimum': 0, 'maximum': 2540},
        bleed_units_per_inch={'const': 2540}, crop_marks=boolean, registration_marks=boolean, preserve_overprints=boolean)
    controls['required'] = list(controls['properties'])
    output['properties']['prepress'] = ref('pdf_prepress')
    output['required'] = list(output['properties'])
    export['api_requirements'] = list(dict.fromkeys(export['api_requirements'] + ['PDFVBASettings.Overprints']))
    export['test_evidence']['sources'] = list(dict.fromkeys(export['test_evidence']['sources'] + ['tests/test_pdf_prepress.py',
        'docs/PDF_PREPRESS.md', 'docs/pdf_prepress_online_evidence.json']))
    export['known_limitations'] = ['Native bleed conversion and mark appearance await consolidated verification.',
        'Bleed is rounded to 10-micrometre units; explicit trim/bleed boxes are required for nonzero bleed or enabled marks.',
        'Artwork bleed coverage, ICC/PDF-X conformance, accurate color/spot/overprint, effective raster DPI and visual/printer acceptance remain unproven.']
    tool = copy.deepcopy(next(t for t in registry['tools'] if t['name'] == 'inspect_pdf'))
    tool.update(name='preflight_pdf', description='Measure all trim/bleed boxes and inventory supported PDF color/spot/image/overprint/output-intent resources.',
                category='pdf_production')
    tool['implementation']['bridge_method'] = 'corel_operator.pdf_prepress.preflight_pdf'
    tool['input_schema'] = obj({'path': local_path, 'expected_trim_sizes': {**nullable(array(size, 500)), 'default': None},
        'expected_bleed_inches': {**nullable({'type': 'number', 'minimum': 0, 'maximum': 1}), 'default': None},
        'require_embedded_fonts': {**boolean, 'default': False}, 'require_output_intent': {**boolean, 'default': False},
        'tolerance_inches': {'type': 'number', 'minimum': .0001, 'maximum': .1, 'default': .001}}, ['path'])
    # Nonempty size arrays match runtime validation.
    tool['input_schema']['properties']['expected_trim_sizes']['anyOf'][0]['minItems'] = 1
    tool['output_schema']['allOf'][1]['then']['properties']['data'] = ref('pdf_prepress')
    tool['test_evidence'] = {'status': 'offline_passed', 'sources': ['tests/test_pdf_prepress.py', 'docs/PDF_PREPRESS.md']}
    tool['known_limitations'] = ['50 MiB/500 pages/10000 resource visits/16 levels; summaries cap at 100; 32 output intents.',
        'Resource inventory observes presence, including unused resources and scoped aliases; artwork streams/inline images/XMP are not decoded.',
        'No effective raster DPI, valid ICC/tint programs, content bleed/mark fidelity or PDF/X/printer guarantee.',
        'Unknown resources and annotations make supported resource inventory incomplete; checks_passed describes only requested geometry/font/intent-presence checks.']
    registry['tools'] = [t for t in registry['tools'] if t['name'] != 'preflight_pdf'] + [tool]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'example.pdf'
        writer = PdfWriter(); writer.add_blank_page(612, 792); writer.write(path)
        prepress = preflight_pdf(str(path))
        inspected = inspect_pdf(str(path), 1, [{'width': 8.5, 'height': 11}], True)
    prepress['path'] = inspected['path'] = 'C:/jobs/controlled.pdf'
    registry['tool_examples']['preflight_pdf'] = {'request': {'path': 'C:/jobs/controlled.pdf'},
        'success': success_result('preflight_pdf', prepress, 1),
        'error': error_result('preflight_pdf', CorelBridgeError('PDF preflight request refused.', ErrorCode.INVALID_ARGUMENT), 1)}
    example = registry['tool_examples']['export_pdf_controlled']['success']['data']
    example.update(path='C:/jobs/controlled.pdf', bytes=prepress['bytes'], inspection=inspected, prepress=copy.deepcopy(prepress))
    example['controls'].update(requested_bleed_inches=0, native_bleed_units=0, bleed_units_per_inch=2540,
                               crop_marks=False, registration_marks=False, preserve_overprints=True)
    example['warnings'] = ['Native/manual prepress acceptance remains deferred.']
    registry_path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')
    api_path = ROOT / 'catalog/coreldraw_x7_api_inventory.json'
    api = json.loads(api_path.read_text(encoding='utf-8'))
    api['catalog_revision'] = '2026-11-05'
    evidence = next(e for e in api['evidence_sources'] if e['id'] == 'x7_pdf_inspection')
    evidence['inspection_date'] = '2026-11-05'
    bleed = next(m for m in api['members'] if m['id'] == 'PDFVBASettings.Bleed')
    bleed['signature'] = 'Bleed get/let VT_INT; installed X7 documentation: bleed amount in tens of micron (2540 units/inch).'
    if not any(m['id'] == 'PDFVBASettings.Overprints' for m in api['members']):
        member = copy.deepcopy(bleed)
        member.update(id='PDFVBASettings.Overprints', signature='Overprints get/let VARIANT_BOOL; preserve document overprints.',
                      docs_url='https://community.coreldraw.com/sdk/api/draw/17/p/pdfvbasettings.overprints')
        api['members'].append(member)
    api_path.write_text(json.dumps(api, indent=2) + '\n', encoding='utf-8')
    matrix_path = ROOT / 'catalog/capability_matrix.csv'
    with matrix_path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    rows = [row for row in rows if row['tool_name'] != 'preflight_pdf']
    rows.append(dict(zip(fields, ['tool.preflight_pdf', 'approved_atomic', 'pdf_production', 'preflight_pdf', 'registered',
        'implemented_unverified', 'read_only', 'P1', 'not_required', 'not_required', 'not_applicable', 'not_required',
        'Bounded supported resource inventory and page boxes do not prove PDF/X or artwork/print fidelity.', 'Consolidated MCP/client artifact review'])))
    for row in rows:
        if row['tool_name'] == 'export_pdf_controlled':
            row['primary_limitation'] = 'Researched 10-micrometre bleed units and measured boxes; native units/marks, ICC/PDF-X and artwork acceptance pending.'
            row['next_verification'] = 'Disposable multipage nonzero-bleed/mark/overprint export, settings restoration and manual prepress review'
    with matrix_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps_path = ROOT / 'catalog/workflow_gaps.json'
    gaps = json.loads(gaps_path.read_text(encoding='utf-8'))
    gaps['research_date'] = '2026-11-05'
    for gap in gaps['gaps']:
        if gap['id'] in ('export_prepress', 'print_production'):
            gap['evidence'] = list(dict.fromkeys(gap.get('evidence', []) + ['docs/PDF_PREPRESS.md', 'tests/test_pdf_prepress.py',
                'docs/x7_pdf_api_evidence.json', 'docs/pdf_prepress_online_evidence.json']))
            gap['implemented_behavior'] = list(dict.fromkeys(gap.get('implemented_behavior', []) + [
                'Researched X7 10-micrometre nonzero PDF bleed and crop/registration/overprint controls with restored settings',
                'All-page measured trim/bleed containment and requested margin verification before exclusive publication']))
            gap['missing_behavior'] = [s for s in gap['missing_behavior'] if s not in ('Proven nonzero bleed and production marks', 'Nonzero bleed and drawn production marks')]
            gap['missing_behavior'] = list(dict.fromkeys(gap['missing_behavior'] + [
                'Native bleed-unit/box/mark verification and artwork bleed/mark appearance acceptance']))
        if gap['id'] == 'export_prepress':
            gap['registered_tools'] = list(dict.fromkeys(gap['registered_tools'] + ['preflight_pdf']))
            gap['implemented_behavior'] = list(dict.fromkeys(gap['implemented_behavior'] + [
                'Bounded supported color/spot/overprint/image/output-intent resource inventory; presence only']))
    gaps_path.write_text(json.dumps(gaps, indent=2) + '\n', encoding='utf-8')
    print('Registered PDF preflight, six strict definitions and researched bleed/mark/overprint export controls.')


if __name__ == '__main__':
    main()
