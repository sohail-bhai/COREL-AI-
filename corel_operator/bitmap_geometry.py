"""Resolution of an affine pixel grid from its measured uncropped quadrilateral."""
from __future__ import annotations

import math


def affine_pixel_resolution(corners, width_pixels, height_pixels, matrix):
    """Map box edges to native affine axes and find the worst directional DPI.

    Coordinates are document inches. Matrix column directions identify pixel X/Y;
    its scale magnitudes are deliberately not applied to already placed edges.
    """
    if (type(corners) is not list or len(corners) != 4 or
        any(type(p) is not dict or set(p) != {'x', 'y'} for p in corners) or
        type(width_pixels) is not int or type(height_pixels) is not int or min(width_pixels, height_pixels) <= 0 or
        not isinstance(matrix, (list, tuple)) or len(matrix) != 6):
        raise ValueError('incomplete_pixel_grid')
    if any(type(v) not in (int, float) or not math.isfinite(v) for p in corners for v in p.values()) or any(
        type(v) not in (int, float) or not math.isfinite(v) for v in matrix):
        raise ValueError('nonfinite_pixel_grid')
    points = [(p['x'], p['y']) for p in corners]
    edges = [(points[(i + 1) % 4][0] - p[0], points[(i + 1) % 4][1] - p[1]) for i, p in enumerate(points)]
    lengths = [math.hypot(*edge) for edge in edges]
    if min(lengths) <= 1e-12:
        raise ValueError('degenerate_pixel_grid')
    coordinate_error = 8 * max(math.ulp(float(value)) for point in points for value in point)
    if coordinate_error > min(lengths) * 1e-4:
        raise ValueError('insufficient_coordinate_precision')
    if any(abs(edges[i][k] + edges[i + 2][k]) > max(coordinate_error, lengths[i] * 1e-7) for i in (0, 1) for k in (0, 1)):
        raise ValueError('non_affine_uncropped_box')
    columns = [(matrix[0], matrix[1]), (matrix[2], matrix[3])]
    column_lengths = [math.hypot(*column) for column in columns]
    cross = lambda a, b: a[0] * b[1] - a[1] * b[0]
    if min(column_lengths) <= 1e-12 or abs(cross(*columns)) <= column_lengths[0] * column_lengths[1] * 1e-8:
        raise ValueError('degenerate_affine_axes')
    if abs(cross(edges[0], edges[1])) <= lengths[0] * lengths[1] * 1e-8:
        raise ValueError('degenerate_pixel_grid')

    def parallel(edge, column):
        return abs(cross(edge, column)) / (math.hypot(*edge) * math.hypot(*column)) <= 1e-6

    candidates = [(edges[0], edges[1])] if parallel(edges[0], columns[0]) and parallel(edges[1], columns[1]) else []
    if parallel(edges[1], columns[0]) and parallel(edges[0], columns[1]):
        candidates.append((edges[1], edges[0]))
    if len(candidates) != 1:
        raise ValueError('unclear_pixel_axis_mapping')
    x_edge, y_edge = candidates[0]
    x_extent, y_extent = math.hypot(*x_edge), math.hypot(*y_edge)
    jx = [v / width_pixels for v in x_edge]; jy = [v / height_pixels for v in y_edge]
    a, d = sum(v * v for v in jx), sum(v * v for v in jy)
    b = sum(x * y for x, y in zip(jx, jy))
    largest_eigenvalue = (a + d + math.hypot(a - d, 2 * b)) / 2
    result = {'axis_dpi': {'x': width_pixels / x_extent, 'y': height_pixels / y_extent},
        'minimum_direction_dpi': 1 / math.sqrt(largest_eigenvalue),
        'pixel_axis_extents_inches': {'x': x_extent, 'y': y_extent}}
    if any(not math.isfinite(v) or v <= 0 for field in ('axis_dpi', 'pixel_axis_extents_inches') for v in result[field].values()) or not math.isfinite(result['minimum_direction_dpi']):
        raise ValueError('nonfinite_resolution')
    return result


def corners_bounds(corners):
    left = min(p['x'] for p in corners); right = max(p['x'] for p in corners)
    bottom = min(p['y'] for p in corners); top = max(p['y'] for p in corners)
    return {'x': left, 'y': bottom, 'width': right - left, 'height': top - bottom}
