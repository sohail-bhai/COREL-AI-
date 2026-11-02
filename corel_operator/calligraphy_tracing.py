"""Deterministic binary-mask tracing for editable calligraphy curves.

The functions in this module do not connect to CorelDRAW.  They turn a retained,
measured silhouette mask into named connected components and closed polygonal
contours that an X7 automation script can map into native curve subpaths.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import hypot
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFilter


Point = tuple[float, float]
Pixel = tuple[int, int]


def extract_warm_calligraphy_mask(
    image: Image.Image,
    *,
    region: tuple[int, int, int, int] = (230, 115, 1035, 624),
    minimum_channel_total: int = 350,
    minimum_red_blue_difference: int = 40,
    neutral_bright_total: int = 660,
    closing_size: int = 5,
) -> tuple[Image.Image, Image.Image]:
    """Extract the warm/bright Arabic silhouette from its measured reference ROI.

    The first mask is the unmodified color classification.  The second applies
    only a small morphological closing to bridge JPEG pinholes; no bitmap is
    ever imported into printable artwork.
    """

    width, height = image.size
    left, top, right, bottom = region
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError(f"Extraction region {region!r} is outside image size {image.size!r}")
    if closing_size < 1 or closing_size % 2 == 0:
        raise ValueError("closing_size must be a positive odd integer")
    crop = image.convert("RGB").crop(region)
    classified = Image.new("L", crop.size, 0)
    classified.putdata([
        255
        if (
            (
                red + green + blue > minimum_channel_total
                and red - blue > minimum_red_blue_difference
            )
            or red + green + blue > neutral_bright_total
        )
        else 0
        for red, green, blue in crop.get_flattened_data()
    ])
    closed = classified
    if closing_size > 1:
        closed = classified.filter(ImageFilter.MaxFilter(closing_size)).filter(
            ImageFilter.MinFilter(closing_size)
        )
    raw = Image.new("L", image.size, 0)
    clean = Image.new("L", image.size, 0)
    raw.paste(classified, (left, top))
    clean.paste(closed, (left, top))
    return raw, clean


def rasterize_pen_commands(
    size: tuple[int, int],
    commands: Iterable[tuple[object, ...]],
    *,
    cubic_steps: int = 24,
) -> Image.Image:
    """Rasterize M/L/C/Z analysis geometry in image-pixel coordinates."""

    if cubic_steps < 2:
        raise ValueError("cubic_steps must be at least 2")
    output = Image.new("L", size, 0)
    draw = ImageDraw.Draw(output)
    points: list[Point] = []
    current: Point | None = None
    for command in commands:
        operation = command[0]
        if operation == "M":
            if points:
                raise ValueError("A subpath must close before another M command")
            current = (float(command[1]), float(command[2]))
            points = [current]
        elif operation == "L" and current is not None:
            current = (float(command[1]), float(command[2]))
            points.append(current)
        elif operation == "C" and current is not None:
            start_x, start_y = current
            control1_x, control1_y = float(command[1]), float(command[2])
            control2_x, control2_y = float(command[3]), float(command[4])
            end_x, end_y = float(command[5]), float(command[6])
            for step in range(1, cubic_steps + 1):
                t = step / cubic_steps
                inverse = 1.0 - t
                points.append((
                    inverse**3 * start_x
                    + 3 * inverse**2 * t * control1_x
                    + 3 * inverse * t**2 * control2_x
                    + t**3 * end_x,
                    inverse**3 * start_y
                    + 3 * inverse**2 * t * control1_y
                    + 3 * inverse * t**2 * control2_y
                    + t**3 * end_y,
                ))
            current = (end_x, end_y)
        elif operation == "Z" and current is not None and len(points) >= 3:
            draw.polygon(points, fill=255)
            points = []
            current = None
        else:
            raise ValueError(f"Invalid or out-of-order pen command: {command!r}")
    if points:
        raise ValueError("Pen commands ended with an open subpath")
    return output


@dataclass(frozen=True)
class MaskComponent:
    """One 8-connected foreground component from a binary mask."""

    label: int
    pixels: tuple[Pixel, ...]
    bbox: tuple[int, int, int, int]

    @property
    def area(self) -> int:
        return len(self.pixels)


@dataclass(frozen=True)
class TracedComponent:
    """A mask component represented by oriented closed boundary loops."""

    label: int
    area: int
    bbox: tuple[int, int, int, int]
    role: str
    loops: tuple[tuple[Point, ...], ...]
    source_nodes: int

    @property
    def node_count(self) -> int:
        return sum(len(loop) for loop in self.loops)

    @property
    def hole_count(self) -> int:
        return sum(signed_area(loop) < 0 for loop in self.loops)


def binary_mask(image: Image.Image, threshold: int = 128) -> Image.Image:
    """Return a strict 0/255 L-mode mask."""

    if not 0 <= threshold <= 255:
        raise ValueError("threshold must be between 0 and 255")
    return image.convert("L").point(lambda value: 255 if value >= threshold else 0)


def connected_components(
    image: Image.Image,
    *,
    threshold: int = 128,
    minimum_area: int = 1,
) -> list[MaskComponent]:
    """Measure foreground components using deterministic 8-connectivity."""

    if minimum_area < 1:
        raise ValueError("minimum_area must be at least 1")
    mask = binary_mask(image, threshold)
    width, height = mask.size
    data = mask.tobytes()
    seen = bytearray(width * height)
    components: list[MaskComponent] = []
    for start in range(width * height):
        if not data[start] or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        pixels: list[Pixel] = []
        left = right = start % width
        top = bottom = start // width
        while queue:
            index = queue.popleft()
            x, y = index % width, index // width
            pixels.append((x, y))
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for ny in range(max(0, y - 1), min(height, y + 2)):
                row = ny * width
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row + nx
                    if not seen[neighbor] and data[neighbor]:
                        seen[neighbor] = 1
                        queue.append(neighbor)
        if len(pixels) >= minimum_area:
            components.append(
                MaskComponent(
                    label=0,
                    pixels=tuple(pixels),
                    bbox=(left, top, right + 1, bottom + 1),
                )
            )
    components.sort(key=lambda item: (-item.area, item.bbox[1], item.bbox[0]))
    return [
        MaskComponent(index, item.pixels, item.bbox)
        for index, item in enumerate(components, start=1)
    ]


def filtered_mask(
    size: tuple[int, int], components: Iterable[MaskComponent]
) -> Image.Image:
    """Rasterize retained component pixels without changing their geometry."""

    output = Image.new("L", size, 0)
    pixels = output.load()
    for component in components:
        for x, y in component.pixels:
            pixels[x, y] = 255
    return output


def signed_area(points: Sequence[Point]) -> float:
    """Return polygon area; positive is clockwise in image coordinates."""

    if len(points) < 3:
        return 0.0
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
    )


def _boundary_edges(component: MaskComponent) -> set[tuple[Pixel, Pixel]]:
    occupied = set(component.pixels)
    edges: set[tuple[Pixel, Pixel]] = set()
    for x, y in occupied:
        if (x, y - 1) not in occupied:
            edges.add(((x, y), (x + 1, y)))
        if (x + 1, y) not in occupied:
            edges.add(((x + 1, y), (x + 1, y + 1)))
        if (x, y + 1) not in occupied:
            edges.add(((x + 1, y + 1), (x, y + 1)))
        if (x - 1, y) not in occupied:
            edges.add(((x, y + 1), (x, y)))
    return edges


def _direction(edge: tuple[Pixel, Pixel]) -> int:
    (x1, y1), (x2, y2) = edge
    delta = (x2 - x1, y2 - y1)
    directions = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    return directions[delta]


def _next_edge(
    incoming: tuple[Pixel, Pixel],
    candidates: Sequence[tuple[Pixel, Pixel]],
) -> tuple[Pixel, Pixel]:
    """Keep foreground on the right at diagonal pixel-touch junctions."""

    current = _direction(incoming)
    priority = {1: 0, 0: 1, 3: 2, 2: 3}  # right, straight, left, reverse
    return min(
        candidates,
        key=lambda edge: (
            priority[(_direction(edge) - current) % 4],
            edge[1][1],
            edge[1][0],
        ),
    )


def boundary_loops(component: MaskComponent) -> list[tuple[Point, ...]]:
    """Trace all oriented outer and hole boundaries for one component."""

    unused = _boundary_edges(component)
    outgoing: dict[Pixel, list[tuple[Pixel, Pixel]]] = defaultdict(list)
    for edge in unused:
        outgoing[edge[0]].append(edge)
    loops: list[tuple[Point, ...]] = []
    while unused:
        first = min(unused)
        edge = first
        points: list[Point] = [first[0]]
        while True:
            if edge not in unused:
                raise ValueError("Boundary graph revisited an edge before closing a loop")
            unused.remove(edge)
            end = edge[1]
            if end == first[0]:
                break
            points.append(end)
            candidates = [candidate for candidate in outgoing[end] if candidate in unused]
            if not candidates:
                raise ValueError("Boundary graph contains an open contour")
            edge = _next_edge(edge, candidates)
        if len(points) >= 3 and signed_area(points):
            loops.append(tuple(points))
    return sorted(loops, key=lambda loop: (-abs(signed_area(loop)), signed_area(loop)))


def _point_line_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = hypot(dx, dy)
    if not length:
        return hypot(point[0] - start[0], point[1] - start[1])
    return abs(
        dy * point[0]
        - dx * point[1]
        + end[0] * start[1]
        - end[1] * start[0]
    ) / length


def _rdp(points: Sequence[Point], tolerance: float) -> list[Point]:
    if len(points) <= 2:
        return list(points)
    start, end = points[0], points[-1]
    distances = [_point_line_distance(point, start, end) for point in points[1:-1]]
    maximum = max(distances, default=0.0)
    if maximum <= tolerance:
        return [start, end]
    split = distances.index(maximum) + 1
    return _rdp(points[: split + 1], tolerance)[:-1] + _rdp(points[split:], tolerance)


def simplify_closed_loop(points: Sequence[Point], tolerance: float) -> tuple[Point, ...]:
    """RDP-simplify a ring while preserving its orientation and closure."""

    if tolerance < 0:
        raise ValueError("tolerance must not be negative")
    ring = list(points)
    if len(ring) <= 3 or not tolerance:
        return tuple(ring)
    anchor = min(range(len(ring)), key=lambda index: (ring[index][1], ring[index][0]))
    ring = ring[anchor:] + ring[:anchor]
    split = max(
        range(1, len(ring)),
        key=lambda index: hypot(ring[index][0] - ring[0][0], ring[index][1] - ring[0][1]),
    )
    first = _rdp(ring[: split + 1], tolerance)
    second = _rdp(ring[split:] + [ring[0]], tolerance)
    simplified = first[:-1] + second[:-1]
    if len(simplified) < 3 or signed_area(simplified) * signed_area(ring) <= 0:
        return tuple(ring)
    return tuple(simplified)


def trace_components(
    components: Sequence[MaskComponent],
    *,
    simplify_tolerance: float = 1.0,
    principal_area: int = 1500,
) -> list[TracedComponent]:
    """Convert measured components to simplified, semantically named traces."""

    if principal_area < 1:
        raise ValueError("principal_area must be at least 1")
    traced: list[TracedComponent] = []
    for component in components:
        source = boundary_loops(component)
        loops = tuple(
            simplify_closed_loop(loop, simplify_tolerance)
            for loop in source
            if len(loop) >= 3
        )
        role = (
            "main_connected_composition"
            if component.label == 1
            else "detached_principal_stroke"
            if component.area >= principal_area
            else "diacritic_or_detached_mark"
        )
        traced.append(
            TracedComponent(
                label=component.label,
                area=component.area,
                bbox=component.bbox,
                role=role,
                loops=loops,
                source_nodes=sum(len(loop) for loop in source),
            )
        )
    return traced


def rasterize_traces(
    size: tuple[int, int], traces: Iterable[TracedComponent]
) -> Image.Image:
    """Rasterize oriented loops for geometry tests and local diagnostics."""

    scale = 2
    high_resolution = Image.new("L", (size[0] * scale, size[1] * scale), 0)
    draw = ImageDraw.Draw(high_resolution)
    loops = [loop for trace in traces for loop in trace.loops]
    for loop in sorted(loops, key=lambda item: abs(signed_area(item)), reverse=True):
        draw.polygon(
            [(x * scale, y * scale) for x, y in loop],
            fill=255 if signed_area(loop) > 0 else 0,
        )
    return high_resolution.transform(
        size,
        Image.Transform.AFFINE,
        (scale, 0, 1, 0, scale, 1),
        resample=Image.Resampling.NEAREST,
    )


def mask_metrics(expected: Image.Image, actual: Image.Image) -> dict[str, float | int]:
    """Return strict pixel overlap metrics for two same-sized binary masks."""

    left = binary_mask(expected)
    right = binary_mask(actual)
    if left.size != right.size:
        raise ValueError(f"Mask dimensions differ: {left.size!r} != {right.size!r}")
    intersection = union = expected_count = actual_count = 0
    for expected_value, actual_value in zip(left.tobytes(), right.tobytes()):
        expected_on = bool(expected_value)
        actual_on = bool(actual_value)
        expected_count += expected_on
        actual_count += actual_on
        intersection += expected_on and actual_on
        union += expected_on or actual_on
    precision = intersection / actual_count if actual_count else 0.0
    recall = intersection / expected_count if expected_count else 0.0
    return {
        "expected_pixels": expected_count,
        "actual_pixels": actual_count,
        "intersection_pixels": intersection,
        "union_pixels": union,
        "iou": intersection / union if union else 1.0,
        "precision": precision,
        "recall": recall,
        "f1": (
            2.0 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        ),
    }


def trace_summary(traces: Sequence[TracedComponent]) -> dict[str, object]:
    """Create JSON-safe trace diagnostics without retaining pixel arrays."""

    return {
        "component_count": len(traces),
        "principal_component_count": sum(
            item.role != "diacritic_or_detached_mark" for item in traces
        ),
        "diacritic_or_mark_count": sum(
            item.role == "diacritic_or_detached_mark" for item in traces
        ),
        "source_boundary_nodes": sum(item.source_nodes for item in traces),
        "simplified_nodes": sum(item.node_count for item in traces),
        "closed_subpaths": sum(len(item.loops) for item in traces),
        "counterform_holes": sum(item.hole_count for item in traces),
        "components": [
            {
                "label": item.label,
                "role": item.role,
                "mask_pixels": item.area,
                "bbox_pixels": list(item.bbox),
                "subpaths": len(item.loops),
                "holes": item.hole_count,
                "nodes": item.node_count,
            }
            for item in traces
        ],
    }
