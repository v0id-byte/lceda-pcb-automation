"""Load LCEDA API dumps (export_geom.js / export_poured.js) into shapely shapes (unit: mil).

load() returns (raw, objs); every obj is a dict:
  kind   'pad' | 'track' | 'via' | 'pour'
  id     pad: '<Designator>.<pad number>', others: primitive id ('<pour id>#k' for pour fills)
  net    net name ('' if none)
  layers copper layer ids the object occupies
  shape  shapely geometry in mil
plus x/y (pads, vias), x1/y1/x2/y2/w (tracks), dia (vias), ref (pads: designator).
"""
import json
import math
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union
from shapely import affinity
from shapely.strtree import STRtree
import cfg

CU = cfg.CU
OUTLINE = cfg.box_mm(0, 0, *cfg.SIZE_MM)
KEEPOUT = unary_union([cfg.box_mm(*k) for k in cfg.CFG['board'].get('keepouts_mm', [])])
# Pour fills stop short of same-net pads (direct-connect spokes are not in the fill data): bridge that gap.
POUR_PAD_TOL = 0.05
# Non-plated slots/pegs inside footprints, [x_mm, y_mm, r_mm]; inflated so the default clearance
# reproduces a typical hole-to-copper rule.
SLOTS = [Point(cfg.X(x), cfg.Y(y)).buffer(r * cfg.MIL + 6.0, 24) for x, y, r in cfg.CFG['board'].get('slots_mm', [])]


def pad_shape(p):
    pd = p['pad'] or ['RECT', 10, 10]
    if pd[0] == 'POLYGON':
        nums = [v for v in pd[1] if isinstance(v, (int, float))]
        s = Polygon(list(zip(nums[0::2], nums[1::2]))).buffer(0)
        # polygon pad paths are in footprint coordinates: recentre on the pad
        b = s.bounds
        s = affinity.translate(s, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
    elif pd[0] == 'ELLIPSE':
        s = Point(0, 0).buffer(pd[1] / 2, 16)
        if len(pd) > 2 and isinstance(pd[2], (int, float)) and pd[2] != pd[1]:
            s = affinity.scale(s, 1, pd[2] / pd[1])
    elif pd[0] == 'OVAL':
        w, h = pd[1], pd[2]
        if w >= h:
            s = LineString([(-(w - h) / 2, 0), ((w - h) / 2, 0)]).buffer(h / 2, 16)
        else:
            s = LineString([(0, -(h - w) / 2), (0, (h - w) / 2)]).buffer(w / 2, 16)
    else:
        w, h = pd[1], pd[2]
        s = Polygon([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)])
    r = p['rot'] or 0
    # older API builds report pad rotation in radians, 4.x reports degrees
    s = affinity.rotate(s, r, origin=(0, 0), use_radians=abs(r) <= 6.3)
    return affinity.translate(s, p['x'], p['y'])


def arc_pts(p0, p1, ang_deg, n=None):
    """points (excluding p0) of an arc from p0 to p1 sweeping ang_deg; positive = centre on the left
    of the chord (verified against LCEDA pour fills: arc centres land on via centres)."""
    th = math.radians(ang_deg)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    c = math.hypot(dx, dy)
    if c < 1e-9 or abs(th) < 1e-6:
        return [p1]
    r = c / (2 * math.sin(abs(th) / 2))
    h = r * math.cos(abs(th) / 2)
    side = 1 if th > 0 else -1
    ox = (p0[0] + p1[0]) / 2 - side * h * dy / c
    oy = (p0[1] + p1[1]) / 2 + side * h * dx / c
    a0 = math.atan2(p0[1] - oy, p0[0] - ox)
    n = n or max(2, int(abs(th) / (math.pi / 16)) + 1)
    pts = [(ox + r * math.cos(a0 + th * k / n), oy + r * math.sin(a0 + th * k / n)) for k in range(1, n)]
    return pts + [p1]


def ring_pts(r, scale=10.0):
    """LCEDA complexPolygon ring (numbers, 'L'/'ARC' markers, unit 10 mil) -> point list in mil.
    'ARC' is followed by the sweep angle (deg) and the end point; the start is the previous point."""
    pts = []
    i = 0
    mode = 'L'
    while i < len(r):
        v = r[i]
        if isinstance(v, str):
            mode = v
            i += 1
            continue
        if mode == 'ARC':
            if i + 2 < len(r) and pts:
                ang = r[i]
                pts += arc_pts(pts[-1], (r[i + 1] * scale, r[i + 2] * scale), ang)
            i += 3
            mode = 'L'
            continue
        pts.append((r[i] * scale, r[i + 1] * scale))
        i += 2
    return pts


def load(geom_path=None, poured_path=None):
    geom_path = geom_path or cfg.path('geom.json')
    poured_path = poured_path or cfg.path('poured.json')
    g = json.load(open(geom_path))['result']
    objs = []
    for c in g['comps']:
        for p in c['pads']:
            layers = CU if p['l'] == 12 else [p['l']]   # 12 = multi-layer (through-hole) pad
            objs.append(dict(kind='pad', id=f"{c['d']}.{p['n']}", net=p['net'] or '', layers=layers,
                             shape=pad_shape(p), ref=c['d'], x=p['x'], y=p['y']))
    for t in g['tracks']:
        if t['l'] not in CU:
            continue
        a, b = (t['x1'], t['y1']), (t['x2'], t['y2'])
        s = LineString([a, b]).buffer(t['w'] / 2, 8) if a != b else Point(*a).buffer(t['w'] / 2, 8)
        objs.append(dict(kind='track', id=t['id'], net=t['net'] or '', layers=[t['l']], shape=s, w=t['w'],
                         x1=t['x1'], y1=t['y1'], x2=t['x2'], y2=t['y2']))
    for t in g.get('arcs', []):  # arc tracks
        if t['l'] not in CU:
            continue
        pts = [(t['x1'], t['y1'])] + arc_pts((t['x1'], t['y1']), (t['x2'], t['y2']), t['ang'])
        objs.append(dict(kind='track', id=t['id'], net=t['net'] or '', layers=[t['l']], shape=LineString(pts).buffer(t['w'] / 2, 8),
                         w=t['w'], x1=t['x1'], y1=t['y1'], x2=t['x2'], y2=t['y2'], arc=t['ang']))
    for v in g['vias']:
        objs.append(dict(kind='via', id=v['id'], net=v['net'] or '', layers=list(CU),
                         shape=Point(v['x'], v['y']).buffer(v['dia'] / 2, 12), x=v['x'], y=v['y'],
                         dia=v['dia'], hole=v.get('hole')))
    if poured_path:
        try:
            pr = json.load(open(poured_path))['result']
        except FileNotFoundError:
            pr = []
        for q in pr:
            for k, f in enumerate(q['fills'] or []):
                if not f:
                    continue
                s = None
                for r in (ring_pts(r) for r in f):
                    if len(r) < 3:
                        continue
                    pg = Polygon(r).buffer(0)
                    s = pg if s is None else s.symmetric_difference(pg)
                if s is None or s.is_empty:
                    continue
                objs.append(dict(kind='pour', id=f"{q['id']}#{k}", net=q['net'] or '', layers=[q['l']], shape=s))
            for k, (lw, cp) in enumerate(q.get('strokes') or []):
                for r in cp or []:
                    pts = ring_pts(r)
                    if len(pts) < 2:
                        continue
                    s = LineString(pts).buffer(max(lw, 0.1) * 10 / 2, 8)
                    objs.append(dict(kind='pour', id=f"{q['id']}#s{k}", net=q['net'] or '', layers=[q['l']], shape=s))
    for k, sl in enumerate(SLOTS):
        objs.append(dict(kind='pad', id=f'SLOT{k}', net='__SLOT', layers=list(CU), shape=sl, ref='__SLOT',
                         x=sl.centroid.x, y=sl.centroid.y))
    return g, objs


def islands(objs, net):
    """Union-find of same-net copper that touches on a shared layer, biggest (by pad count) first.

    Geometric only: LCEDA's DRC is stricter (a track end that stops mid-segment on another track
    or on a via is NOT connected for DRC). Treat DRC as the truth, this as a fast pre-check.
    """
    o = [x for x in objs if x['net'] == net]
    par = list(range(len(o)))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    tree = STRtree([x['shape'] for x in o])
    for i, x in enumerate(o):
        for j in tree.query(x['shape'].buffer(POUR_PAD_TOL)):
            j = int(j)
            if j <= i:
                continue
            y = o[j]
            if set(x['layers']) & set(y['layers']) and x['shape'].distance(y['shape']) < POUR_PAD_TOL:
                a, b = f(i), f(j)
                if a != b:
                    par[a] = b
    groups = {}
    for i in range(len(o)):
        groups.setdefault(f(i), []).append(o[i])
    return sorted(groups.values(), key=lambda g: (-sum(1 for x in g if x['kind'] == 'pad'), -len(g)))
