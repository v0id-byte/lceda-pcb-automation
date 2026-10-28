"""stitch.py NET [--n 4] [--near x,y] [--r 3] [--via 20,36] [--in-pad PAD] [--layers 1,2] [--pitch 0.9] [--commit]

Add parallel vias to a net where it already has copper on BOTH given layers (default top + bottom),
e.g. a power net that changes layer through a single via, or a ground spine. Candidates are scanned on a
0.1 mm grid within --r mm of --near, must sit fully inside the net's copper on both layers, keep the
clearance rules on every layer (plane-layer ground pour re-carves around new vias), keep hole-to-hole
spacing, and are picked closest-first at least --pitch mm apart.

--in-pad PAD : thermal vias inside a pad (e.g. a QFN exposed pad); via-in-pad is allowed only there.
"""
import argparse, math
import _boot  # noqa: F401
import cfg, router, check
from shapely.geometry import Point
from shapely.ops import unary_union
import eda

ap = argparse.ArgumentParser()
ap.add_argument('net'); ap.add_argument('--n', type=int, default=4); ap.add_argument('--near'); ap.add_argument('--r', type=float, default=3)
ap.add_argument('--via', default=','.join(map(str, cfg.VIA))); ap.add_argument('--in-pad'); ap.add_argument('--layers', default=f'{cfg.CU[0]},{cfg.CU[-1]}')
ap.add_argument('--pitch', type=float, default=0.9); ap.add_argument('--hole-clr', type=float, default=14, help='mil, hole edge to hole edge')
ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
V = tuple(float(v) for v in a.via.split(',')); Ls = [int(x) for x in a.layers.split(',')]
B = router.Board(); objs = B.all_objs()
own = [o for o in objs if o['net'] == a.net and o['kind'] in ('track', 'pour', 'pad', 'via')]
need = V[1] / 2 + 0.5
if a.in_pad:
    pad = [o for o in objs if o['id'] == a.in_pad][0]
    area = pad['shape'].buffer(-need)
    cx, cy = pad['shape'].centroid.x, pad['shape'].centroid.y
else:
    area = None
    for L in Ls:
        cu = unary_union([o['shape'] for o in own if L in o['layers']])
        cu = cu.buffer(-need)
        area = cu if area is None else area.intersection(cu)
    # no via inside SMD pads of the net (solder wicking)
    area = area.difference(unary_union([o['shape'].buffer(V[1] / 2 + 2) for o in own if o['kind'] == 'pad' and len(o['layers']) == 1]))
    cx, cy = (cfg.X(float(a.near.split(',')[0])), cfg.Y(float(a.near.split(',')[1]))) if a.near else (area.centroid.x, area.centroid.y)
if a.near and a.in_pad:
    cx, cy = cfg.X(float(a.near.split(',')[0])), cfg.Y(float(a.near.split(',')[1]))
holes = [(o['x'], o['y'], (o.get('hole') or 12)) for o in objs if o['kind'] == 'via'] + \
        [(o['x'], o['y'], 30) for o in objs if o['kind'] == 'pad' and len(o['layers']) > 1]
cands = []
step = 0.1 * cfg.MIL; R = a.r * cfg.MIL; k = int(R / step)
for i in range(-k, k + 1):
    for j in range(-k, k + 1):
        x, y = cx + i * step, cy + j * step
        d = math.hypot(x - cx, y - cy)
        if d <= R and area.contains(Point(x, y)):
            cands.append((d, x, y))
cands.sort()
picked = []
for d, x, y in cands:
    if len(picked) >= a.n:
        break
    if any(math.hypot(x - px, y - py) < a.pitch * cfg.MIL for px, py in picked):
        continue
    if any(math.hypot(x - hx, y - hy) < (hd + V[0]) / 2 + a.hole_clr for hx, hy, hd in holes):
        continue
    clr = cfg.CLR_STRONG if a.net in cfg.STRONG else cfg.CLR
    cf = [c for c in check.conflicts(B, a.net, [('V', x, y)], clr - 0.02, 0, V, via_thru_pour=tuple(cfg.PLANES)) if c[1] != 'pour' or a.net != cfg.GND]
    cf = [c for c in cf if not (a.in_pad and c[1] == 'pad' and c[2] == a.in_pad)]
    if cf:
        continue
    picked.append((x, y)); holes.append((x, y, V[0])); B.add_via(a.net, x, y, *V)
print(a.net, 'vias:', [cfg.mm(x, y, 2) for x, y in picked], f'({len(cands)} candidate points)')
if a.commit and picked:
    print('COMMIT', eda.commit_items(a.net, [('V', x, y) for x, y in picked], 0, V))
