"""place_route.py DES --center x,y [--r 6] [--reach 6] [--sides 2,1] [--step 0.2] [--layers 1,2,16] [--n 400] [--gap 0.1] [--commit]

Find a placement for a (small) part where it is legal AND every pad can actually be routed to the
rest of its net. fit.py only proves the footprint fits; in a dense area that is not enough (the part
can fit in a pocket nothing can reach). Footprint outlines (pads + silkscreen, from js/comp_bbox.js)
of parts on the same side must stay --gap mm apart, so silkscreen does not overlap either. Candidates are tried nearest-first; the first one whose pads
all route (with the router, inside a local window) wins. With --commit the part is moved and the
routes are written.

After a side change LCEDA may mirror the footprint differently from the prediction: the committed pad
positions are compared with the plan and, for 2-pad parts, the rotation is flipped by 180 deg if the
pads came out swapped.
"""
import argparse, json, math
import _boot  # noqa: F401
import cfg, router, check, pcbgeo, eda, bodies
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union

ap = argparse.ArgumentParser()
ap.add_argument('des'); ap.add_argument('--center', required=True); ap.add_argument('--r', type=float, default=6)
ap.add_argument('--sides', default='2,1'); ap.add_argument('--step', type=float, default=0.2)
ap.add_argument('--layers', default=','.join(map(str, cfg.ROUTE_LAYERS))); ap.add_argument('--w', type=float, default=8)
ap.add_argument('--n', type=int, default=400, help='max candidates to route-test'); ap.add_argument('--reach', type=float, default=6, help='mm: route to net copper within this distance'); ap.add_argument('--commit', action='store_true'); ap.add_argument('--debug', action='store_true'); ap.add_argument('--avoid', default='', help='PAD[,PAD..]:mm keep every pad of the part this far from those pads'); ap.add_argument('--gap', type=float, default=0.1, help='mm between footprint outlines')
ap.add_argument('--holes', default='', help='footprint NPTH holes/pegs as dx,dy,dia[;...] mm in the footprint frame (they go through every layer)')
ap.add_argument('--hole-clr', type=float, default=0.3, help='mm from a hole to any copper')
ap.add_argument('--widths', default='', help='per-net track width, NET:mil[,NET:mil] (default --w)')
ap.add_argument('--windows', default='1.5', type=lambda v: [float(x) for x in v.split(',')], help='mm margins of the routing window to try, e.g. 1.5,4,8')
ap.add_argument('--first', default='', help='route the pads on these nets first (comma list): a wide route can wall in the next pad')
ap.add_argument('--body', action='store_true', help='keep estimated bodies apart (board without silkscreen) instead of outlines')
a = ap.parse_args()
cx, cy = map(float, a.center.split(','))
WN = {k: float(v) for k, v in (x.rsplit(':', 1) for x in a.widths.split(',') if x)}
wfor = lambda net: WN.get(net, a.w); Ls = tuple(int(x) for x in a.layers.split(','))
B0 = router.Board(); objs = B0.all_objs()
comp = [c for c in B0.g['comps'] if c['d'] == a.des][0]
mine = [o for o in objs if o.get('ref') == a.des]
others = [o for o in objs if o.get('ref') != a.des and o['kind'] != 'pour']
# Footprint outlines (pads + silkscreen) from LCEDA: parts on the same side must not overlap them
# (pitfalls #27). Falls back to pad extents if the export fails.
fb = eda.run('comp_bbox.js', 300)
FOOT = {f['d']: f for f in (fb.get('result') or [])} if fb.get('success') else {}
if a.body:
    for f in FOOT.values():
        f['box'] = bodies.body_box(f)[0]
mbox = lambda f: box(cfg.X(f['box'][0]), cfg.Y(f['box'][3]), cfg.X(f['box'][2]), cfg.Y(f['box'][1]))
court = {1: [], 2: []}
for c in B0.g['comps']:
    if c['d'] == a.des:
        continue
    ps = [o for o in objs if o['kind'] == 'pad' and o.get('ref') == c['d']]
    if c['d'] in FOOT:
        court[FOOT[c['d']]['layer']].append(mbox(FOOT[c['d']]))
        if FOOT[c['d']]['tht']:   # through-hole pads also block the other side
            court[3 - FOOT[c['d']]['layer']].append(box(*unary_union([p['shape'] for p in ps]).bounds))
    elif ps:
        b = box(*unary_union([p['shape'] for p in ps]).bounds)
        for s in ([1, 2] if any(len(p['layers']) > 1 for p in ps) else [ps[0]['layers'][0]]):
            court[s].append(b)


def shapes(x, y, rot, side):
    out = []
    for p in mine:
        s = affinity.translate(p['shape'], -comp['x'], -comp['y'])
        s = affinity.rotate(s, -comp['r'], origin=(0, 0))
        if side != comp['l'] and len(p['layers']) == 1:
            s = affinity.scale(s, -1, 1, origin=(0, 0))
        s = affinity.translate(affinity.rotate(s, rot, origin=(0, 0)), cfg.X(x), cfg.Y(y))
        out.append((p, s))
    return out


from shapely.geometry import Point
HOLES = [tuple(map(float, h.split(','))) for h in a.holes.split(';') if h.strip()]


def holes_at(x, y, rot, side):
    out = []
    for dx, dy, dia in HOLES:
        h = Point(dx * cfg.MIL, dy * cfg.MIL).buffer(dia / 2 * cfg.MIL, 24)
        if side == 2:   # footprint frame -> bottom side is mirrored
            h = affinity.scale(h, -1, 1, origin=(0, 0))
        out.append(affinity.translate(affinity.rotate(h, rot, origin=(0, 0)), cfg.X(x), cfg.Y(y)))
    return out


AV = []
if a.avoid:
    names, dist = a.avoid.rsplit(':', 1)
    AV = [(o, float(dist) * cfg.MIL) for o in objs if o['id'] in names.split(',')]
cands = []
why = {'edge': 0, 'footprint': 0, 'avoid': 0, 'copper': 0, 'holes': 0}
k = int(a.r / a.step)
for side in [int(s) for s in a.sides.split(',')]:
    for i in range(-k, k + 1):
        for j in range(-k, k + 1):
            x, y = cx + i * a.step, cy + j * a.step
            if math.hypot(x - cx, y - cy) > a.r:
                continue
            for rot in (0, 90, 180, 270):
                sh = shapes(x, y, rot, side)
                cb = box(*unary_union([s for _, s in sh]).bounds)
                if a.des in FOOT:   # own footprint outline, moved like the pads
                    fo = affinity.translate(mbox(FOOT[a.des]), -comp['x'], -comp['y'])
                    fo = affinity.rotate(fo, -comp['r'], origin=(0, 0))
                    if side != comp['l']:
                        fo = affinity.scale(fo, -1, 1, origin=(0, 0))
                    cb = box(*affinity.translate(affinity.rotate(fo, rot, origin=(0, 0)), cfg.X(x), cfg.Y(y)).bounds)
                cb = cb.buffer(a.gap * cfg.MIL, join_style=2)
                if not pcbgeo.OUTLINE.buffer(-cfg.EDGE).contains(cb) or cb.intersects(pcbgeo.KEEPOUT):
                    why['edge'] += 1; continue
                if any(cb.intersects(c) for c in court[side]):
                    why['footprint'] += 1; continue
                if any(o['shape'].distance(s) < dd for o, dd in AV for _, s in sh):
                    why['avoid'] += 1; continue
                if any(o['net'] != p['net'] and side in o['layers'] and o['shape'].distance(s) < router.pclr(cfg.CLR + 0.3, o['net'])
                       for p, s in sh for o in others):
                    why['copper'] += 1; continue
                hs = holes_at(x, y, rot, side)
                if any(h.distance(o['shape']) < a.hole_clr * cfg.MIL for h in hs for o in others) or \
                        any(h.intersects(c) for h in hs for c in court[3 - side]):
                    why['holes'] += 1; continue
                cands.append((math.hypot(x - cx, y - cy), x, y, rot, side, sh, hs))
cands.sort(key=lambda c: c[0])
print('legal placements', len(cands), 'rejected', why)
found = None
for d, x, y, rot, side, sh, hs in cands[:a.n]:
    B = router.Board(); B.remove(lambda o: o.get('ref') == a.des)
    for k, h in enumerate(hs):   # holes block routing on every layer
        B.objs.append(dict(kind='pad', id=f'{a.des}.HOLE{k}', net='__SLOT', layers=list(cfg.CU), shape=h.buffer(max(0.0, a.hole_clr * cfg.MIL - cfg.CLR)), ref='__SLOT', x=h.centroid.x, y=h.centroid.y))
    placed = []
    for p, s in sh:
        q = dict(p, shape=s, layers=(p['layers'] if len(p['layers']) > 1 else [side])); B.objs.append(q); placed.append(q)
    plan = []
    first = a.first.split(',') if a.first else []
    for q in sorted(placed, key=lambda q: q['net'] not in first):
        if not q['net']:
            continue
        allisl = B.islands(q['net'])
        own = next(i for i in allisl if any(o is q for o in i))
        if len(own) > 1 and own is allisl[0]:   # already joined to the main copper (e.g. lands on its pour)
            continue
        isl = [i for i in allisl if not any(o is q for o in i)]
        if not isl:
            continue
        # ground is joined by the pour (passable for the router): any ground copper is a valid target
        pool = [o for i in isl for o in i] if q['net'] == cfg.GND else max(isl, key=len)
        dst = [o for o in pool if o['kind'] in ('pad', 'track', 'via') and o['shape'].distance(q['shape']) < a.reach * cfg.MIL]
        if not dst:
            if a.debug: print(' ', round(x, 2), round(y, 2), rot, side, q['id'], q['net'], 'no net copper within --reach')
            plan = None; break
        bb = unary_union([q['shape']] + [o['shape'] for o in dst]).bounds
        for m in [v * cfg.MIL for v in a.windows]:   # grow the search window like route_net
            res, msg = router.route(B, q['net'], [q], dst, w=wfor(q['net']), clr=cfg.CLR + 0.3, window=(bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m),
                                    layers=Ls, via=cfg.via_for(q['net']), via_cost=15, via_thru_pour=tuple(cfg.PLANES), maxexp=60000 if m < 2 * cfg.MIL else 400000,
                                    clr_track=(cfg.CLR_STRONG + 0.3 if q['net'] in cfg.STRONG else None))
            if res:
                break
        if not res:
            if a.debug: print(' ', round(x, 2), round(y, 2), rot, side, q['id'], q['net'], msg, len(dst))
            plan = None; break
        items = [(r[0], r[1], r[2], r[3], r[4], r[5], wfor(q['net'])) if r[0] == 'T' else r for r in res]
        cf = [c for c in check.conflicts(B, q['net'], items, cfg.CLR - 0.02, wfor(q['net'])) if c[1] != 'pour']
        if cf:
            if a.debug: print(' ', round(x, 2), round(y, 2), rot, side, q['id'], q['net'], 'conflicts', cf[:2])
            plan = None; break
        for it in items:
            (B.add_via(q['net'], it[1], it[2], *cfg.via_for(q['net'])) if it[0] == 'V' else B.add_track(q['net'], *it[1:6], it[6]))
        plan.append((q, items))
    if plan is not None:
        found = (x, y, rot, side, plan, sh); break
if not found:
    raise SystemExit('no routable placement found')
x, y, rot, side, plan, sh = found
print('PLACE', a.des, [round(x, 2), round(y, 2), rot, side], {q['id']: cfg.mm(q['shape'].centroid.x, q['shape'].centroid.y, 2) for q, _ in plan})
if a.commit:
    r = eda.run('rip_move.js', 120, {'mv': {a.des: [x, y, rot, side]}})['result']['moved'][a.des]
    got = {f"{a.des}.{n}": (px, py) for n, px, py, _ in r}
    want = {p['id']: cfg.mm(s.centroid.x, s.centroid.y, 2) for p, s in sh}   # every pad, routed or not
    if any(math.hypot(got[k][0] - v[0], got[k][1] - v[1]) > 0.05 for k, v in want.items() if k in got):
        if len(mine) != 2:
            raise SystemExit(f'pads landed differently than planned: {got} vs {want}; fix rotation by hand')
        r = eda.run('rip_move.js', 120, {'mv': {a.des: [x, y, (rot + 180) % 360, side]}})['result']['moved'][a.des]
        print('flipped 180 to match plan', r)
    for q, items in plan:
        print('COMMIT', q['id'], eda.commit_items(q['net'], items, wfor(q['net'])).get('success'))
