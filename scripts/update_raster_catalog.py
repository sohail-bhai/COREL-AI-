"""Register local raster contracts/examples without connecting to CorelDRAW."""
from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from corel_operator.raster_assets import inspect_raster_asset, prepare_raster_asset
from corel_operator.results import success_result, error_result
from corel_operator.errors import CorelBridgeError, ErrorCode
from corel_operator.vector_geometry import fingerprint


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required, 'additionalProperties': False}


def nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


def ref(name):
    return {'$ref': '#/schema_definitions/' + name}


def main():
    path = ROOT / 'catalog/mcp_tool_registry.json'
    registry = json.loads(path.read_text(encoding='utf-8'))
    string = {'type': 'string', 'maxLength': 1000}
    boolean = {'type': 'boolean'}
    digest = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    local_path = {'type': 'string', 'minLength': 1, 'maxLength': 32767}
    pixel = {'type': 'integer', 'minimum': 1, 'maximum': 65535}
    coordinate = {'type': 'integer', 'minimum': 0, 'maximum': 65535}
    warnings = {'type': 'array', 'items': string, 'maxItems': 20}
    definitions = {
        'raster_pixel_size': obj({'width': pixel, 'height': pixel}),
        'raster_crop_box': obj({key: coordinate for key in ('left', 'top', 'right', 'bottom')}),
        'raster_metadata_dpi': obj({key: {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 1000000} for key in ('x', 'y')}),
        'raster_icc_metadata': obj({'present': boolean, 'bytes': {'type': 'integer', 'minimum': 0, 'maximum': 8388608}, 'sha256': nullable(digest)}),
        'raster_alpha_metadata': obj({'present': boolean, 'minimum': nullable({'type': 'integer', 'minimum': 0, 'maximum': 255}),
                                     'maximum': nullable({'type': 'integer', 'minimum': 0, 'maximum': 255})}),
        'raster_asset': obj({'schema': {'const': 'raster-asset-v1'}, 'path': local_path,
            'bytes': {'type': 'integer', 'minimum': 1, 'maximum': 134217728}, 'source_sha256': digest,
            'format': {'enum': ['PNG', 'JPEG', 'TIFF', 'BMP', 'GIF']}, 'native_mode': {'type': 'string', 'maxLength': 32},
            'mode': {'type': 'string', 'maxLength': 32}, 'native_size_pixels': ref('raster_pixel_size'),
            'size_pixels': ref('raster_pixel_size'), 'pixels_sha256': digest,
            'exif_orientation': {'type': 'integer', 'minimum': 1, 'maximum': 8},
            'exif_orientation_applied': boolean, 'has_multiple_frames': boolean,
            'metadata_dpi': nullable(ref('raster_metadata_dpi')), 'icc_profile': ref('raster_icc_metadata'),
            'alpha': ref('raster_alpha_metadata'), 'preparation_supported': boolean,
            'unsupported_reasons': {'type': 'array', 'items': {'enum': ['multi_frame_source_requires_explicit_frame_workflow',
                'source_mode_requires_precision_or_color_workflow']}, 'maxItems': 2, 'uniqueItems': True}, 'fingerprint': digest}),
        'raster_inspection_result': obj({'asset': ref('raster_asset'), 'verification_status': {'const': 'implemented_unverified'}, 'warnings': warnings}),
        'raster_preparation_operations': obj({'crop_box': nullable(ref('raster_crop_box')),
            'rotation_degrees': {'enum': [0, 90, 180, 270]}, 'flip_horizontal': boolean, 'flip_vertical': boolean,
            'before_resize_pixels': ref('raster_pixel_size'), 'target_size': nullable(ref('raster_pixel_size')),
            'resize_mode': {'enum': ['contain', 'cover', 'stretch']}, 'fitting_crop_box': nullable(ref('raster_crop_box')),
            'resampling': {'enum': ['nearest', 'bicubic', 'lanczos']}, 'upscaled': boolean}),
        'raster_preparation_result': obj({'prepared': {'const': True}, 'source': ref('raster_asset'), 'output': ref('raster_asset'),
            'operations': ref('raster_preparation_operations'),
            'source_preservation': obj({'source_written': {'const': False}, 'byte_hash_verified': {'const': True}}),
            'pixel_readback_verified': {'const': True}, 'verification_status': {'const': 'implemented_unverified'}, 'warnings': warnings}),
    }
    registry['schema_definitions'].update(definitions)
    request_properties = {'source_path': local_path, 'destination_path': local_path, 'expected_source_fingerprint': digest,
        'crop_box': {**nullable(ref('raster_crop_box')), 'default': None},
        'rotation_degrees': {'enum': [0, 90, 180, 270], 'default': 0},
        'flip_horizontal': {**boolean, 'default': False}, 'flip_vertical': {**boolean, 'default': False},
        'target_size': {**nullable(ref('raster_pixel_size')), 'default': None},
        'resize_mode': {'enum': ['contain', 'cover', 'stretch'], 'default': 'contain'},
        'allow_upscale': {**boolean, 'default': False},
        'resampling': {'enum': ['nearest', 'bicubic', 'lanczos'], 'default': 'lanczos'},
        'output_dpi': {**nullable({'type': 'number', 'minimum': 1, 'maximum': 2400}), 'default': None}}
    base = copy.deepcopy(next(tool for tool in registry['tools'] if tool['name'] == 'inspect_pdf'))
    names = ('inspect_raster_asset', 'prepare_raster_asset')
    new_tools = []
    for name in names:
        tool = copy.deepcopy(base)
        tool.update(name=name, category='images', description='Inspect an immutable raster snapshot and decoded EXIF-normalized pixel provenance.' if name == names[0]
                    else 'Prepare a new source-preserving PNG/TIFF with verified pixel, ICC/DPI and source readback.',
                    permission='read_only' if name == names[0] else 'export', risk='low' if name == names[0] else 'medium')
        tool['implementation']['bridge_method'] = 'corel_operator.raster_assets.' + name
        tool['input_schema'] = obj({'source_path': local_path}) if name == names[0] else obj(request_properties,
                ['source_path', 'destination_path', 'expected_source_fingerprint'])
        tool['output_schema']['allOf'][1]['then']['properties']['data'] = ref('raster_inspection_result' if name == names[0] else 'raster_preparation_result')
        tool['test_evidence'] = {'status': 'offline_passed', 'sources': ['tests/test_raster_assets.py', 'docs/RASTER_PREPARATION.md',
                                    'docs/raster_preparation_online_evidence.json']}
        tool['known_limitations'] = ['128 MiB encoded/64 million pixels/65535 per side/8 MiB ICC limits; sources PNG/JPEG/TIFF/BMP/GIF.',
            'Preparation accepts single-frame RGB/RGBA/L/LA/CMYK; palette/bitonal sources normalize, precision and multiple frames require separate workflows.',
            'PNG/TIFF only; CMYK uses TIFF. Opaque ICC bytes and recognized DPI are retained without conversion or print approval.',
            'No background removal, tracing, AI enhancement, native bitmap mutation or document-wide raster preflight.',
            'Filesystem ownership and source hashes are checked at bounded observations; paths are not locked against concurrent external edits.',
            'Consolidated MCP client, Corel import and visual/artifact review remain deferred.']
        new_tools.append(tool)
    registry['tools'] = [tool for tool in registry['tools'] if tool['name'] not in names] + new_tools
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / 'source.png'; output = Path(temporary) / 'prepared.png'
        with Image.new('RGBA', (4, 3), (30, 90, 180, 128)) as image:
            image.save(source, dpi=(300, 300))
        inspected = inspect_raster_asset(str(source))
        prepared = prepare_raster_asset(str(source), str(output), inspected['asset']['fingerprint'],
            crop_box={'left': 1, 'top': 0, 'right': 4, 'bottom': 2}, rotation_degrees=90)
    def example_asset(asset, path):
        asset['path'] = path
        asset.pop('fingerprint')
        asset['fingerprint'] = fingerprint(asset)
    example_asset(inspected['asset'], 'C:/jobs/source.png')
    example_asset(prepared['source'], 'C:/jobs/source.png')
    example_asset(prepared['output'], 'C:/jobs/prepared.png')
    for name, data, request in [(names[0], inspected, {'source_path': 'C:/jobs/source.png'}),
                               (names[1], prepared, {'source_path': 'C:/jobs/source.png', 'destination_path': 'C:/jobs/prepared.png',
                                 'expected_source_fingerprint': inspected['asset']['fingerprint'],
                                 'crop_box': {'left': 1, 'top': 0, 'right': 4, 'bottom': 2}, 'rotation_degrees': 90})]:
        registry['tool_examples'][name] = {'request': request, 'success': success_result(name, data, 1),
            'error': error_result(name, CorelBridgeError('Raster request was refused.', ErrorCode.INVALID_ARGUMENT), 1)}
    path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')
    matrix_path = ROOT / 'catalog/capability_matrix.csv'
    with matrix_path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
    rows = [row for row in rows if row['tool_name'] not in names]
    for name in names:
        rows.append(dict(zip(fields, ['tool.' + name, 'approved_atomic', 'images', name, 'registered', 'implemented_unverified',
            'read_only' if name == names[0] else 'export', 'P1', 'not_required', 'not_required', 'not_applicable', 'not_required',
            'Local metadata/pixel checks do not establish color/source-detail/print or Corel import fidelity.',
            'Consolidated MCP client plus prepared raster import/artifact review'])))
    with matrix_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields); writer.writeheader(); writer.writerows(rows)
    gaps_path = ROOT / 'catalog/workflow_gaps.json'
    gaps = json.loads(gaps_path.read_text(encoding='utf-8'))
    images = next(gap for gap in gaps['gaps'] if gap['id'] == 'images')
    images['registered_tools'] = list(dict.fromkeys(images['registered_tools'] + list(names)))
    images['missing_behavior'] = ['Background removal/cleanup and AI enhancement',
        'Document-wide native raster preflight and source-detail/color/visual verification', 'Bounded tracing and fidelity reporting']
    images['evidence'] = list(dict.fromkeys(images.get('evidence', []) + ['docs/RASTER_PREPARATION.md', 'tests/test_raster_assets.py',
        'docs/raster_preparation_online_evidence.json']))
    gaps_path.write_text(json.dumps(gaps, indent=2) + '\n', encoding='utf-8')
    print('Registered two API-free raster tools and nine strict result definitions.')


if __name__ == '__main__': main()
