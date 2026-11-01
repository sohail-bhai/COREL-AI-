"""Extract exact vector calligraphy curves from the uploaded photo into a clean SVG."""
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
output_dir = ROOT / "output"
output_dir.mkdir(exist_ok=True)

mask_path = output_dir / "calligraphy_mask.png"
if not mask_path.exists():
    raise FileNotFoundError("calligraphy_mask.png not found")

mask = Image.open(mask_path).convert("L")
w, h = mask.size

# Isolate calligraphy strokes (y > 70 to skip lattice at top)
grid = [[1 if (y > 70 and mask.getpixel((x, y)) > 128) else 0 for x in range(w)] for y in range(h)]

table = {
    1: [(3, 2)], 2: [(2, 1)], 3: [(3, 1)], 4: [(1, 0)],
    5: [(3, 0), (1, 2)], 6: [(2, 0)], 7: [(3, 0)], 8: [(0, 3)],
    9: [(0, 2)], 10: [(0, 1), (2, 3)], 11: [(0, 1)], 12: [(1, 3)],
    13: [(1, 2)], 14: [(2, 3)]
}

adj = defaultdict(list)
for y in range(h - 1):
    for x in range(w - 1):
        val = (grid[y][x] << 3) | (grid[y][x+1] << 2) | (grid[y+1][x+1] << 1) | grid[y+1][x]
        for e1, e2 in table.get(val, []):
            pts = {0: (x + 0.5, y), 1: (x + 1.0, y + 0.5), 2: (x + 0.5, y + 1.0), 3: (x, y + 0.5)}
            p1, p2 = pts[e1], pts[e2]
            adj[p1].append(p2)

# Chain into closed loops
visited = set()
loops = []
for start in list(adj.keys()):
    if start in visited:
        continue
    loop = [start]
    visited.add(start)
    curr = start
    while True:
        next_pts = [p for p in adj.get(curr, []) if p not in visited]
        if not next_pts:
            if start in adj.get(curr, []):
                loops.append(loop)
            break
        curr = next_pts[0]
        visited.add(curr)
        loop.append(curr)

def rdp(pts, eps=1.0):
    if len(pts) <= 2:
        return pts
    p1, p2 = pts[0], pts[-1]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    norm = math.hypot(dx, dy)
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        if norm == 0:
            d = math.hypot(pts[i][0] - p1[0], pts[i][1] - p1[1])
        else:
            d = abs(dy * pts[i][0] - dx * pts[i][1] + p2[0]*p1[1] - p2[1]*p1[0]) / norm
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(pts[:idx+1], eps)[:-1] + rdp(pts[idx:], eps)
    return [p1, p2]

valid_loops = [rdp(l, 1.0) for l in loops if len(l) > 12]
print(f"Extracted {len(valid_loops)} vector loops for the Arabic Calligraphy.")

# Generate SVG
paths = []
for loop in valid_loops:
    d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in loop) + " Z"
    paths.append(d)

all_d = " ".join(paths)
svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <path d="{all_d}" fill="#E1C382" fill-rule="evenodd" stroke="#C3964B" stroke-width="0.5"/>
</svg>"""

out_svg = output_dir / "alhamdulillah_calligraphy.svg"
out_svg.write_text(svg_content, encoding="utf-8")
print(f"SUCCESS: Wrote vector SVG to {out_svg} ({len(svg_content)} chars)")
