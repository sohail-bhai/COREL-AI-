"""Complete repeated-artwork sheet plans and measured affine copy comparisons."""
from __future__ import annotations

import copy
import json
import math
import re

from .errors import CorelBridgeError, ErrorCode
from .object_references import validate_reference
from .vector_geometry import fingerprint, paths_match, seal
from .workflows import calculate_sheet_layout

MAX_RUN_COPIES = 500
MAX_RUN_NODES = 50000
MAX_REPEAT_NODES = 1000
MAX_REPEAT_SEGMENTS = 10000
MAX_REPEAT_BYTES = 8 * 1024 * 1024
TOLERANCE = .00001


def invalid(message):
    raise CorelBridgeError(message, ErrorCode.INVALID_ARGUMENT)


def tree_nodes(tree):
    stack = [(tree, 0)]
    seen = set()
    while stack:
        node, depth = stack.pop()
        if type(node) is not dict or id(node) in seen or len(seen) >= MAX_REPEAT_NODES or depth > 32:
            invalid('Repeat trees require at most 1000 distinct nodes and 32 levels.')
        seen.add(id(node))
        yield node
        for key in ('clip_children', 'group_children'):
            children = node[key]
            if type(children) is not list or len(children) > MAX_REPEAT_NODES:
                invalid('Repeat child collections are malformed or exceed their limit.')
            stack.extend((child, depth+1) for child in reversed(children))


def validate_repeat(repeat):
    if type(repeat) is not dict or set(repeat) != {'schema', 'object_reference', 'bounds_inches', 'node_count', 'segment_count', 'tree', 'verification_scope', 'unchecked_checks', 'fingerprint'}:
        invalid('Supply the complete current inspect_print_repeat manifest.')
    try:
        nodes = list(tree_nodes(repeat['tree']))
        encoded = json.dumps(repeat, sort_keys=True, allow_nan=False)
        if len(encoded.encode('utf-8')) > MAX_REPEAT_BYTES: invalid('The print repeat manifest exceeds 8 MiB.')
        repeat = copy.deepcopy(repeat)
        expected = repeat.pop('fingerprint')
        if repeat['schema'] != 'print-repeat-v1' or type(expected) is not str or fingerprint(repeat) != expected:
            invalid('The print repeat manifest changed; inspect it again.')
        validate_reference(repeat['object_reference'])
        if repeat['object_reference']['shape_identity'] != repeat['tree']['identity']:
            invalid('Print repeat source identity disagrees with its complete tree.')
        bounds = repeat['bounds_inches']
        if type(bounds) is not dict or set(bounds) != {'x', 'y', 'width', 'height'} or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 10000 for v in bounds.values()) or bounds['width'] <= 0 or bounds['height'] <= 0:
            invalid('The print repeat requires readable positive physical bounds.')
        nodes = list(tree_nodes(repeat['tree']))
        if type(repeat['node_count']) is not int or not 1 <= repeat['node_count'] <= MAX_REPEAT_NODES or len(nodes) != repeat['node_count']:
            invalid('The complete print repeat must contain 1-1000 native shapes.')
        identities = [node['identity'] for node in nodes]
        if len(set(identities)) != len(identities) or any(type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value) for value in identities):
            invalid('Print repeat native identities are ambiguous or malformed.')
        if type(repeat['segment_count']) is not int or not 0 <= repeat['segment_count'] <= MAX_REPEAT_SEGMENTS:
            invalid('Print repeat curve data exceeds 10000 segments.')
        if sum(node['curve']['segment_count'] for node in nodes if node.get('curve') is not None) != repeat['segment_count']:
            invalid('Print repeat segment totals disagree with its complete tree.')
        if repeat['verification_scope'] != 'measured_native_repeat' or repeat['unchecked_checks'] != UNCHECKED_CHECKS:
            invalid('Print repeat verification scope changed; inspect it again.')
        for node in nodes:
            transform = node['transform']
            component = transform['bounds_inches']
            if type(component) is not dict or set(component) != {'x', 'y', 'width', 'height'} or any(
                type(value) not in (int, float) or not math.isfinite(value) for value in component.values()) or component['width'] < 0 or component['height'] < 0:
                invalid('Print repeat component bounds must be complete, finite and nonnegative in size.')
            if node['supported_payload'] is not True or type(node['effects_count']) is not int or node['effects_count'] != 0:
                invalid('Print repeats require supported payloads without live effects.')
            if node['fill']['type_code'] not in (0, 1, 2) or node['outline']['type_code'] not in (0, 1):
                invalid('Print repeats support no/uniform/fountain fills and no/uniform outlines.')
            if node['gradient']['complete'] is not True:
                invalid('Print repeat fill evidence is incomplete.')
            if node['clip_children'] and node['contents_locked'] is not True:
                invalid('Lock PowerClip contents before planning a print repeat.')
            if not close_numbers(transform['matrix'], transform['matrix']) or len(transform['matrix']) != 6:
                invalid('Print repeat affine transforms must contain six finite numbers.')
        if repeat['tree']['transform']['bounds_inches'] != bounds:
            invalid('Print repeat bounds disagree with the complete source tree.')
        return {**repeat, 'fingerprint': expected}
    except CorelBridgeError: raise
    except Exception as exc:
        raise CorelBridgeError('The print repeat manifest is malformed.', ErrorCode.INVALID_ARGUMENT) from exc


def plan_print_run(repeat, copies, sheet_width_inches, sheet_height_inches, margin_inches=.25,
                   gutter_inches=.125, rotation_policy='never', sheet_orientation='fixed',
                   margin_left_inches=None, margin_top_inches=None, margin_right_inches=None,
                   margin_bottom_inches=None, gripper_inches=0., gripper_edge='bottom',
                   mark_clearance_inches=0., object_name_prefix='Print_Run'):
    repeat = validate_repeat(repeat)
    if type(copies) is not int or not 1 <= copies <= MAX_RUN_COPIES:
        invalid('copies must be an integer in [1, 500].')
    if repeat['node_count'] * copies > MAX_RUN_NODES:
        invalid('The run exceeds 50000 output shapes; split the quantity into smaller runs.')
    if type(object_name_prefix) is not str or not object_name_prefix.strip() or len(object_name_prefix) > 100 or any(ord(c) < 32 for c in object_name_prefix):
        invalid('object_name_prefix requires 1-100 characters without controls.')
    if any(type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 200 for value in (sheet_width_inches, sheet_height_inches)):
        invalid('Sheet dimensions must be finite in (0, 200] inches.')
    request = {'repeat': repeat, 'copies': copies, 'sheet_width_inches': sheet_width_inches, 'sheet_height_inches': sheet_height_inches,
        'margin_inches': margin_inches, 'gutter_inches': gutter_inches, 'rotation_policy': rotation_policy,
        'sheet_orientation': sheet_orientation, 'margin_left_inches': margin_left_inches, 'margin_top_inches': margin_top_inches,
        'margin_right_inches': margin_right_inches, 'margin_bottom_inches': margin_bottom_inches,
        'gripper_inches': gripper_inches, 'gripper_edge': gripper_edge, 'mark_clearance_inches': mark_clearance_inches,
        'object_name_prefix': object_name_prefix}
    bounds = repeat['bounds_inches']
    layout = calculate_sheet_layout(bounds['width'], bounds['height'], sheet_width_inches, sheet_height_inches,
        margin_inches, gutter_inches, rotation_policy=rotation_policy, sheet_orientation=sheet_orientation,
        margin_left_inches=margin_left_inches, margin_top_inches=margin_top_inches,
        margin_right_inches=margin_right_inches, margin_bottom_inches=margin_bottom_inches,
        gripper_inches=gripper_inches, gripper_edge=gripper_edge, mark_clearance_inches=mark_clearance_inches,
        requested_quantity=copies)
    capacity = layout['capacity']
    if not capacity: invalid('No repeat fits the requested sheet and production margins.')
    per_sheet = min(capacity, copies)
    if len(layout['placements']) < per_sheet: invalid('The planner did not expose every used sheet position.')
    placements = []
    for index in range(copies):
        position = copy.deepcopy(layout['placements'][index % capacity])
        for key in ('x', 'y', 'width', 'height'):
            position[key] = position.pop(key+'_inches')
        position.update(copy_index=index+1, page_index=index//capacity+1,
            slot_index=index%capacity+1, object_name=f'{object_name_prefix.strip()}_{index+1:03d}')
        placements.append(position)
    sheets = []
    for index in range(math.ceil(copies/capacity)):
        count = min(capacity, copies-index*capacity)
        sheets.append({'page_index': index+1, 'first_copy_index': index*capacity+1,
            'last_copy_index': index*capacity+count, 'copy_count': count, 'unused_capacity': capacity-count,
            'partial': count < capacity, 'width_inches': layout['sheet_width_inches'], 'height_inches': layout['sheet_height_inches']})
    return seal({'schema': 'print-run-plan-v1', 'request': request,
        'summary': {'requested_copies': copies, 'produced_copies': copies, 'overage': 0, 'sheet_count': len(sheets),
            'capacity_per_sheet': capacity, 'output_shape_count': copies*repeat['node_count']},
        'layout': {key: value for key, value in layout.items() if key not in ('placements', 'total_produced', 'overage')},
        'sheets': sheets, 'placements': placements, 'scale_percent': 100., 'bleed_inches': 0.,
        'production_ready': False, 'verification_status': 'implemented_unverified',
        'warnings': ['The final sheet uses only the remaining requested copies; no padded copies or overage are created.',
            'Repeat size is preserved; prepare the desired physical size before inspection. Rotations are 0/90 degrees.',
            'Nonzero bleed, production marks, outline-aware bounds, source pixels, color/glyph/visual fidelity and printer approval remain separate checks.']})


def validate_run_plan(plan, approved_fingerprint):
    if type(plan) is not dict or type(approved_fingerprint) is not str or not re.fullmatch('[0-9a-f]{64}', approved_fingerprint):
        invalid('Supply the complete print run and its approved fingerprint.')
    try:
        plan = copy.deepcopy(plan)
        if plan.get('schema') != 'print-run-plan-v1' or plan.get('fingerprint') != approved_fingerprint:
            invalid('The print run fingerprint differs from the approved plan.')
        rebuilt = plan_print_run(**plan['request'])
        if rebuilt != plan:
            invalid('Print run geometry, quantities or source changed; plan and approve it again.')
        return plan
    except CorelBridgeError: raise
    except Exception as exc:
        raise CorelBridgeError('The print run plan is malformed.', ErrorCode.INVALID_ARGUMENT) from exc


def point_map(point, matrix):
    a, b, c, d, x, y = matrix
    return {'x': a*point['x']+c*point['y']+x, 'y': b*point['x']+d*point['y']+y}


def bounds_map(bounds, matrix):
    corners = [point_map({'x': bounds['x']+u, 'y': bounds['y']+v}, matrix)
        for u, v in ((0, 0), (bounds['width'], 0), (bounds['width'], bounds['height']), (0, bounds['height']))]
    xs, ys = [p['x'] for p in corners], [p['y'] for p in corners]
    return {'x': min(xs), 'y': min(ys), 'width': max(xs)-min(xs), 'height': max(ys)-min(ys)}


def matrix_map(matrix, outer):
    a, b, c, d, x, y = matrix; p, q, r, s, tx, ty = outer
    return [p*a+r*b, q*a+s*b, p*c+r*d, q*c+s*d, p*x+r*y+tx, q*x+s*y+ty]


def placement_map(bounds, placement):
    angle = placement.get('rotation_degrees', 0)
    if angle not in (0, 90): invalid('Print run rotations must be 0 or 90 degrees.')
    outer = [1., 0., 0., 1., 0., 0.] if angle == 0 else [0., 1., -1., 0., 0., 0.]
    rotated = bounds_map(bounds, outer)
    outer[4] = placement['x']-rotated['x']; outer[5] = placement['y']-rotated['y']
    return outer


def close_numbers(left, right):
    return len(left) == len(right) and all(type(a) in (int, float) and type(b) in (int, float) and
        math.isfinite(a) and math.isfinite(b) and abs(a-b) <= TOLERANCE for a, b in zip(left, right))


UNCHECKED_CHECKS = ['bitmap_pixels_and_link_freshness', 'text_run_formatting_and_glyphs',
    'rendered_clipping_and_visual_fidelity', 'outline_aware_trim_and_bleed',
    'color_overprint_and_printer_approval']


def close_bounds(left, right):
    return close_numbers([left[k] for k in ('x', 'y', 'width', 'height')], [right[k] for k in ('x', 'y', 'width', 'height')])


def paths_map(paths, outer):
    paths = copy.deepcopy(paths)
    for path in paths:
        path['start'] = point_map(path['start'], outer)
        for segment in path['segments']:
            for key in ('end', 'control1', 'control2'):
                if key in segment: segment[key] = point_map(segment[key], outer)
    return paths


def compare_gradient(before, after, outer):
    if before is None or after is None: return before == after
    left, right = copy.deepcopy(before), copy.deepcopy(after)
    source, actual = left['gradient'], right['gradient']
    if source is None or actual is None: return left == right
    coordinates = source.pop('coordinates_inches'); actual_coordinates = actual.pop('coordinates_inches')
    angle = source.pop('angle_degrees'); actual_angle = actual.pop('angle_degrees')
    if left != right: return False
    angle_delta = math.degrees(math.atan2(outer[1], outer[0]))
    if not any(abs((actual_angle-candidate+180) % 360-180) <= TOLERANCE for candidate in (angle, angle+angle_delta)): return False
    transformed = {}
    for prefix in ('Start', 'End', 'End2'):
        point = point_map({'x': coordinates[prefix+'X'], 'y': coordinates[prefix+'Y']}, outer)
        transformed.update({prefix+'X': point['x'], prefix+'Y': point['y']})
    return any(close_numbers([candidate[k] for k in coordinates], [actual_coordinates[k] for k in coordinates]) for candidate in (coordinates, transformed))


def verify_repeat_copy(source, actual, outer, root_name=None, expected_root_matrix=None):
    """Match metadata and full paths plus placed/local native coordinate observations."""
    before = list(tree_nodes(source)); after = list(tree_nodes(actual))
    if len(before) != len(after): invalid('A native print copy changed complete tree membership.')
    for index, (left, right) in enumerate(zip(before, after)):
        for key in ('shape_type_code', 'contents_locked', 'fill', 'outline', 'transparency', 'text', 'bitmap', 'effects_count'):
            if left.get(key) != right.get(key): invalid('A native print copy changed measured source body or paint metadata.')
        if index == 0 and root_name is not None:
            if right['object_name'] != root_name: invalid('A print output lost its planned object name.')
        elif left['name_sha256'] != right['name_sha256']:
            invalid('A print copy changed an original component name.')
        if any(len(left[key]) != len(right[key]) for key in ('group_children', 'clip_children')):
            invalid('A print copy changed group/PowerClip topology.')
        expected_bounds = bounds_map(left['transform']['bounds_inches'], outer)
        actual_bounds = right['transform']['bounds_inches']
        global_bounds = close_bounds(expected_bounds, actual_bounds)
        local_bounds = index > 0 and close_bounds(left['transform']['bounds_inches'], actual_bounds)
        if not global_bounds and not local_bounds: invalid('A print copy changed component geometry or placement.')
        expected_matrix = matrix_map(left['transform']['matrix'], outer)
        if index == 0 and expected_root_matrix is not None: expected_matrix = expected_root_matrix
        if not close_numbers(expected_matrix, right['transform']['matrix']) and not (
            index > 0 and local_bounds and close_numbers(left['transform']['matrix'], right['transform']['matrix'])):
            invalid('A print copy changed its native affine transform.')
        a, b = left.get('curve'), right.get('curve')
        if (a is None) != (b is None): invalid('A print copy changed curve availability.')
        if a is not None:
            if any(a[key] != b[key] for key in ('node_types', 'node_count', 'segment_count')) or not (
                paths_match(a['paths'], b['paths']) or paths_match(paths_map(a['paths'], outer), b['paths'])):
                invalid('A print copy changed complete line/cubic geometry or node metadata.')
        if not compare_gradient(left.get('gradient'), right.get('gradient'), outer): invalid('A print copy changed gradient parameters, stops or coordinate geometry.')
    return True
