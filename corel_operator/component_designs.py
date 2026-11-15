"""Immutable local component plans, revision chains and provider requests.

No COM, network, model API, raster generation or existing-file overwrite occurs.
Local plans remain drafts until native/layout/production acceptance is reviewed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid

from .design_plans import validate_design_plan, _validate_design_plan_schema
from .errors import CorelBridgeError, ErrorCode
from .raster_assets import inspect_raster_asset
from .typography import finite_number

MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_REVISIONS = 64
HASH = re.compile(r'[0-9a-f]{64}\Z')
UNCHECKED = ['native_composition', 'text_fit_and_glyphs', 'visual_layout', 'color_and_print_acceptance']


def invalid(message, code=ErrorCode.INVALID_ARGUMENT, details=None):
    raise CorelBridgeError(message, code, details)


def canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise CorelBridgeError('Component data must be finite bounded JSON.', ErrorCode.INVALID_ARGUMENT) from exc
    if len(raw) > MAX_JSON_BYTES:
        invalid('Component history exceeds the 5 MiB limit.')
    return raw


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(value):
    result = copy.deepcopy(value)
    result['fingerprint'] = digest(value)
    return result


def json_path(value):
    if (type(value) is not str or not value or len(value) > 32767
            or any(ord(c) < 32 for c in value) or value.startswith(('\\\\', '//'))):
        invalid('Choose an absolute local JSON path without control characters.')
    path = Path(value).expanduser()
    if not path.is_absolute() or path.suffix.lower() != '.json':
        invalid('Component plans and requests require an absolute .json path.')
    if os.name == 'nt' and (path.is_reserved() or ':' in path.name):
        invalid('Device names and alternate streams are unsupported.')
    return path


def _unique_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            invalid('Component JSON contains an ambiguous duplicate key.')
        value[key] = item
    return value


def _read(path):
    try:
        resolved = path.resolve(strict=True)
        json_path(str(resolved))
        with resolved.open('rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_JSON_BYTES:
                invalid('Component JSON must be an ordinary file within 5 MiB.')
            raw = stream.read(MAX_JSON_BYTES + 1)
            after = os.fstat(stream.fileno())
        receipt = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, hashlib.sha256(raw).hexdigest())
        if (len(raw) != before.st_size or len(raw) > MAX_JSON_BYTES
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            invalid('Component JSON changed during inspection.')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_keys)
        canonical(value)
        return value, resolved, receipt
    except CorelBridgeError:
        raise
    except Exception as exc:
        raise CorelBridgeError('Component JSON could not be read safely.', ErrorCode.UNSAFE_PATH) from exc


def asset_receipts(plan):
    result, cache = {}, {}
    for element in plan['elements']:
        if element['type'] != 'artwork':
            continue
        path = element['file_path']
        if Path(path).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif'}:
            invalid('Component artwork currently supports fingerprinted raster sources; vector import requires a separate payload workflow.',
                    ErrorCode.UNSUPPORTED_IN_PROFILE)
        if path not in cache:
            asset = inspect_raster_asset(path)['asset']
            if not asset['preparation_supported']:
                invalid('Component assets require supported single-frame raster preparation.', ErrorCode.UNSUPPORTED_IN_PROFILE)
            cache[path] = {key: asset[key] for key in ('path', 'source_sha256', 'pixels_sha256', 'size_pixels', 'fingerprint')}
        result[element['id']] = cache[path]
    return result


def _checked_plan(plan):
    canonical(plan)
    _validate_design_plan_schema(plan)
    assets = asset_receipts(plan)  # Validate local paths before general file preflight.
    result = validate_design_plan(plan)
    if not result['ready_for_execution']:
        invalid('Component plan contains blocking layout or asset issues.')
    return assets


def _validate_manifest(value, check_assets=True):
    if (type(value) is not dict or set(value) != {'schema', 'design_id', 'revision', 'history', 'fingerprint'}
            or value['schema'] != 'component-design-v1' or type(value['design_id']) is not str
            or not re.fullmatch('[0-9a-f]{32}', value['design_id'])
            or type(value['revision']) is not int or type(value['history']) is not list
            or not 1 <= len(value['history']) <= MAX_REVISIONS or value['revision'] != len(value['history']) - 1):
        invalid('Invalid bounded component design manifest.')
    previous = None
    for index, row in enumerate(value['history']):
        if (type(row) is not dict or set(row) != {'revision', 'parent_fingerprint', 'action', 'changed_component_ids',
                'plan', 'asset_receipts', 'fingerprint'} or row['revision'] != index
                or type(row['revision']) is not int or row['parent_fingerprint'] != previous
                or row['action'] not in ('create', 'replace', 'restore', 'resize')
                or type(row['changed_component_ids']) is not list
                or len(row['changed_component_ids']) > 200 or type(row['asset_receipts']) is not dict
                or any(type(key) is not str or not 1 <= len(key) <= 64 for key in row['changed_component_ids'])
                or len(set(row['changed_component_ids'])) != len(row['changed_component_ids'])
                or (index == 0) != (row['action'] == 'create')):
            invalid('Invalid component revision chain.')
        _validate_design_plan_schema(row['plan'])
        if index and row['action'] == 'replace':
            prior_plan = value['history'][index - 1]['plan']
            prior = {e['id']: e for e in prior_plan['elements']}
            future = {e['id']: e for e in row['plan']['elements']}
            if (len(row['changed_component_ids']) != 1 or prior.keys() != future.keys()
                    or any(prior[key] != future[key] for key in prior if key not in row['changed_component_ids'])
                    or {k: v for k, v in prior_plan.items() if k != 'elements'}
                    != {k: v for k, v in row['plan'].items() if k != 'elements'}
                    or [e['id'] for e in prior_plan['elements']] != [e['id'] for e in row['plan']['elements']]):
                invalid('A replacement revision changed an unapproved component or layout.')
        base = {key: item for key, item in row.items() if key != 'fingerprint'}
        if row['fingerprint'] != digest(base):
            invalid('Component revision fingerprint does not match its content.')
        previous = row['fingerprint']
    if value['fingerprint'] != digest({key: item for key, item in value.items() if key != 'fingerprint'}):
        invalid('Component manifest fingerprint does not match its content.')
    current = value['history'][-1]
    if check_assets and _checked_plan(current['plan']) != current['asset_receipts']:
        invalid('A component asset changed; create a reviewed replacement revision.')
    return current


def _source(path, expected=None):
    value, resolved, receipt = _read(json_path(path))
    _validate_manifest(value)
    if expected is not None and (type(expected) is not str or not HASH.fullmatch(expected) or expected != value['fingerprint']):
        invalid('Component design changed; inspect the current fingerprint again.')
    return value, resolved, receipt


def _source_unchanged(source):
    if source is None:
        return
    _, path, receipt = source
    if _read(path)[2] != receipt:
        invalid('Component source changed during publication.')
    _validate_manifest(source[0])


def _publish(value, destination_path, source=None, validator=None):
    destination = json_path(destination_path)
    if destination.exists():
        invalid('Refusing to overwrite an existing component file.', ErrorCode.OUTPUT_EXISTS)
    raw = canonical(value) + b'\n'
    if len(raw) > MAX_JSON_BYTES:
        invalid('Component output exceeds the JSON byte limit.')
    output_receipt = None
    published = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = destination.parent.resolve(strict=True) / destination.name
        with tempfile.TemporaryDirectory(prefix='component-stage-', dir=destination.parent) as folder:
            stage = Path(folder) / 'snapshot.json'
            stage.write_bytes(raw)
            if stage.read_bytes() != raw:
                invalid('Component staging readback failed.')
            _source_unchanged(source)
            if validator is not None:
                validator(value)
            stage_stat = stage.stat()
            output_receipt = (stage_stat.st_dev, stage_stat.st_ino, stage_stat.st_size,
                              stage_stat.st_mtime_ns, hashlib.sha256(raw).hexdigest())
            os.link(stage, destination)  # Atomic non-overwrite publication on local NTFS.
            published = True
            observed, _, receipt = _read(destination)
            if observed != value or receipt != output_receipt:
                invalid('Component publication identity/content readback failed.')
            _source_unchanged(source)
            if validator is not None:
                validator(value)
        return str(destination)
    except Exception as exc:
        cleanup_verified = not published
        if published:
            try:
                _, _, receipt = _read(destination)
                if receipt == output_receipt:
                    destination.unlink()
                    cleanup_verified = not destination.exists()
            except Exception:
                pass
        code = ErrorCode.OUTPUT_EXISTS if isinstance(exc, FileExistsError) else (
            exc.code if isinstance(exc, CorelBridgeError) else ErrorCode.UNSAFE_PATH)
        raise CorelBridgeError('Component publication failed; uncertain concurrent output is preserved.', code,
                               {'cleanup_verified': cleanup_verified, 'output_may_remain': published and not cleanup_verified}) from exc


def _result(value, path):
    current = value['history'][-1]
    return {'path': path, 'fingerprint': value['fingerprint'], 'revision': value['revision'],
            'component_count': len(current['plan']['elements']), 'plan': current['plan'],
            'changed_component_ids': current['changed_component_ids'], 'history_count': len(value['history']),
            'verification_status': 'implemented_unverified', 'unchecked_checks': list(UNCHECKED)}


def create_component_design(plan, destination_path):
    assets = _checked_plan(plan)
    row = seal({'revision': 0, 'parent_fingerprint': None, 'action': 'create',
                'changed_component_ids': [element['id'] for element in plan['elements']],
                'plan': copy.deepcopy(plan), 'asset_receipts': assets})
    value = seal({'schema': 'component-design-v1', 'design_id': uuid.uuid4().hex, 'revision': 0, 'history': [row]})
    return _result(value, _publish(value, destination_path, validator=_validate_manifest))


def inspect_component_design(path):
    value, resolved, _ = _source(path)
    result = _result(value, str(resolved))
    result['history'] = [{'revision': row['revision'], 'action': row['action'], 'fingerprint': row['fingerprint'],
                          'changed_component_ids': row['changed_component_ids']} for row in value['history']]
    return result


def _append(source, destination_path, plan, action, changed):
    value = copy.deepcopy(source[0])
    if len(value['history']) >= MAX_REVISIONS:
        invalid('Start a separately reviewed design after 64 revisions.')
    assets = _checked_plan(plan)
    index = len(value['history'])
    row = seal({'revision': index, 'parent_fingerprint': value['history'][-1]['fingerprint'],
                'action': action, 'changed_component_ids': changed, 'plan': plan, 'asset_receipts': assets})
    value['history'].append(row)
    value['revision'] = index
    value.pop('fingerprint')
    value = seal(value)
    return _result(value, _publish(value, destination_path, source, _validate_manifest))


def revise_component_design(source_path, destination_path, expected_fingerprint, component_id=None,
                            replacement_element=None, restore_revision=None):
    source = _source(source_path, expected_fingerprint)
    value, current = source[0], source[0]['history'][-1]['plan']
    if restore_revision is not None:
        if (type(restore_revision) is not int or not 0 <= restore_revision < len(value['history'])
                or component_id is not None or replacement_element is not None):
            invalid('Choose one existing revision to restore, without replacement fields.')
        restored = value['history'][restore_revision]
        plan = copy.deepcopy(restored['plan'])
        if _checked_plan(plan) != restored['asset_receipts']:
            invalid('Historical component assets changed or are unavailable; restore refused.')
        previous = {e['id']: e for e in current['elements']}
        future = {e['id']: e for e in plan['elements']}
        changed = sorted(key for key in previous.keys() | future.keys() if previous.get(key) != future.get(key))
        return _append(source, destination_path, plan, 'restore', changed)
    if (type(component_id) is not str or not 1 <= len(component_id) <= 64
            or type(replacement_element) is not dict or replacement_element.get('id') != component_id):
        invalid('Supply a component ID and a replacement element with the same ID.')
    plan = copy.deepcopy(current)
    matches = [index for index, element in enumerate(plan['elements']) if element['id'] == component_id]
    if len(matches) != 1:
        invalid('The component ID is absent or ambiguous.')
    plan['elements'][matches[0]] = copy.deepcopy(replacement_element)
    return _append(source, destination_path, plan, 'replace', [component_id])


def resize_component_design(source_path, destination_path, expected_fingerprint, width_inches, height_inches,
                            minimum_font_size_points=8., minimum_image_dpi=300.):
    width = finite_number(width_inches, 'width_inches', .001, 200)
    height = finite_number(height_inches, 'height_inches', .001, 200)
    minimum = finite_number(minimum_font_size_points, 'minimum_font_size_points', 1, 500)
    dpi = finite_number(minimum_image_dpi, 'minimum_image_dpi', 1, 2400)
    source = _source(source_path, expected_fingerprint)
    plan = copy.deepcopy(source[0]['history'][-1]['plan'])
    old_width, old_height = plan['canvas']['width_inches'], plan['canvas']['height_inches']
    ratio = min(width / old_width, height / old_height)
    dx, dy = (width - old_width * ratio) / 2, (height - old_height * ratio) / 2
    replacements = []
    for element in plan['elements']:
        if element['type'] == 'artwork' and not all(key in element for key in ('x_inches', 'y_inches', 'width_inches', 'height_inches')):
            invalid('Resize requires explicit placed artwork dimensions.', ErrorCode.UNSUPPORTED_IN_PROFILE)
        for key, offset in (('x_inches', dx), ('y_inches', dy)):
            if key in element: element[key] = element[key] * ratio + offset
        for key in ('width_inches', 'height_inches'):
            if key in element: element[key] *= ratio
        if 'outline' in element:
            element['outline']['width_points'] *= ratio
        if element['type'] == 'text':
            size = element.get('font_size_points', 24.) * ratio
            if size < minimum:
                invalid('Resize would make editable text smaller than the explicit minimum.')
            element['font_size_points'] = size
        if element['type'] == 'artwork':
            asset = source[0]['history'][-1]['asset_receipts'][element['id']]
            if min(asset['size_pixels']['width'] / element['width_inches'],
                   asset['size_pixels']['height'] / element['height_inches']) < dpi:
                replacements.append(element['id'])
    plan['canvas'].update(width_inches=width, height_inches=height)
    result = _append(source, destination_path, plan, 'resize', [e['id'] for e in plan['elements']])
    result.update(scale_factor=ratio, requires_higher_resolution_components=replacements,
                  minimum_image_dpi=dpi, minimum_font_size_points=minimum)
    return result


def prepare_component_generation(source_path, component_id, expected_fingerprint, prompt, destination_path,
                                 width_pixels=1024, height_pixels=1024):
    if type(prompt) is not str or not prompt.strip() or len(prompt) > 4000 or '\x00' in prompt:
        invalid('Supply a component prompt with 1–4000 characters and no NUL.')
    if any(type(value) is not int or not 1 <= value <= 16384 for value in (width_pixels, height_pixels)):
        invalid('Generation dimensions must be integers from 1 to 16384 pixels.')
    if width_pixels * height_pixels > 64_000_000:
        invalid('Generation request exceeds 64 million pixels.')
    source = _source(source_path, expected_fingerprint)
    plan = source[0]['history'][-1]['plan']
    selected = [element for element in plan['elements'] if element['id'] == component_id]
    if len(selected) != 1:
        invalid('The requested component ID does not exist.')
    request = seal({'schema': 'component-generation-request-v1', 'provider': 'local_asset_handoff',
        'design_id': source[0]['design_id'], 'source_design_fingerprint': expected_fingerprint,
        'component_id': component_id, 'current_component': selected[0], 'prompt': prompt,
        'width_pixels': width_pixels, 'height_pixels': height_pixels,
        'provider_connected': False, 'generated': False, 'network_request_sent': False})
    path = _publish(request, destination_path, source)
    return {'path': path, 'request': request, 'fingerprint': request['fingerprint'], 'provider_connected': False,
            'generated': False, 'network_request_sent': False, 'verification_status': 'implemented_unverified'}
