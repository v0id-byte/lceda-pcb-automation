"""place_route.py DES --center x,y [--r 6] [--reach 6] [--sides 2,1] [--step 0.2] [--layers 1,2,16] [--n 400] [--commit]

Find a placement for a (small) part where it is legal AND every pad can actually be routed to the
rest of its net. fit.py only proves the footprint fits; in a dense area that is not enough (the part
can fit in a pocket nothing can reach). Candidates are tried nearest-first; the first one whose pads
all route (with the router, inside a local window) wins. With --commit the part is moved and the
routes are written.

After a side change LCEDA may mirror the footprint differently from the prediction: the committed pad
positions are compared with the plan and, for 2-pad parts, the rotation is flipped by 180 deg if the
pads came out swapped.
"""
import argparse, json, math
import _boot  # noqa: F401
import cfg, router, check, pcbgeo, eda
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union

ap = argparse.ArgumentParser()
ap.add_argument('des'); ap.add_argument('--center', required=True); ap.add_argument('--r', type=float, default=6)
ap.add_argument('--sides', default='2,1'); ap.add_argument('--step', type=float, default=0.2)
ap.add_argument('--layers', default=','.join(map(str, cfg.ROUTE_LAYERS))); ap.add_argument('--w', type=float, default=8)
ap.add_argument('--n', type=int, default=400, help='max candidates to route-test'); ap.add_argument('--reach', type=float, default=6, help='mm: route to net copper within this distance'); ap.add_argument('--commit', action='store_true'); ap.add_argument('--debug', action='store_true'); ap.add_argument('--avoid', default='', help='PAD[,PAD..]:mm keep every pad of the part this far from those pads')
a = ap.parse_args()
cx, cy = map(float, a.center.split(',')); Ls = tuple(int(x) for x in a.layers.split(','))
B0 = router.Board(); objs = B0.all_objs()
comp = [c for c in B0.g['comps'] if c['d'] == a.des][0]
mine = [o for o in objs if o.get('ref') == a.des]
others = [o for o in objs if o.get('ref') != a.des and o['kind'] != 'pour']
court = {1: [], 2: []}
for c in B0.g['comps']:
    if c['d'] == a.des:
        continue
    ps = [o for o in objs if o['kind'] == 'pad' and o.get('ref') == c['d']]
    if ps:
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


AV = []
if a.avoid:
    names, dist = a.avoid.rsplit(':', 1)
    AV = [(o, float(dist) * cfg.MIL) for o in objs if o['id'] in names.split(',')]
cands = []
k = int(a.r / a.step)
for side in [int(s) for s in a.sides.split(',')]:
    for i in range(-k, k + 1):
        for j in range(-k, k + 1):
            x, y = cx + i * a.step, cy + j * a.step
            if math.hypot(x - cx, y - cy) > a.r:
                continue
            for rot in (0, 90, 180, 270):
                sh = shapes(x, y, rot, side)
                cb = box(*unary_union([s for _, s in sh]).bounds).buffer(0.15 * cfg.MIL)
                if not pcbgeo.OUTLINE.buffer(-cfg.EDGE).contains(cb) or cb.intersects(pcbgeo.KEEPOUT) or any(cb.intersects(c) for c in court[side]):
                    continue
                if any(o['shape'].distance(s) < dd for o, dd in AV for _, s in sh):
                    continue
                if any(o['net'] != p['net'] and side in o['layers'] and o['shape'].distance(s) < router.pclr(cfg.CLR + 0.3, o['net'])
                       for p, s in sh for o in others):
                    continue
                cands.append((math.hypot(x - cx, y - cy), x, y, rot, side, sh))
cands.sort(key=lambda c: c[0])
print('legal placements', len(cands))
found = None
for d, x, y, rot, side, sh in cands[:a.n]:
    B = router.Board(); B.remove(lambda o: o.get('ref') == a.des)
    placed = []
    for p, s in sh:
        q = dict(p, shape=s, layers=(p['layers'] if len(p['layers']) > 1 else [side])); B.objs.append(q); placed.append(q)
    plan = []
    for q in placed:
        if not q['net']:
            continue
        isl = [i for i in B.islands(q['net']) if not any(o is q for o in i)]
        if not isl:
            continue
        dst = [o for o in max(isl, key=len) if o['kind'] in ('pad', 'track', 'via') and o['shape'].distance(q['shape']) < a.reach * cfg.MIL]
        if not dst:
            plan = None; break
        bb = unary_union([q['shape']] + [o['shape'] for o in dst]).bounds; m = 1.5 * cfg.MIL
        res, msg = router.route(B, q['net'], [q], dst, w=a.w, clr=cfg.CLR + 0.3, window=(bb[0] - m, bb[1] - m, bb[2] + m, bb[3] + m),
                                layers=Ls, via_cost=15, via_thru_pour=tuple(cfg.PLANES), maxexp=60000)
        if not res:
            if a.debug: print(' ', round(x, 2), round(y, 2), rot, side, q['id'], q['net'], msg, len(dst))
            plan = None; break
        items = [(r[0], r[1], r[2], r[3], r[4], r[5], a.w) if r[0] == 'T' else r for r in res]
        if [c for c in check.conflicts(B, q['net'], items, cfg.CLR - 0.02, a.w) if c[1] != 'pour']:
            plan = None; break
        for it in items:
            (B.add_via(q['net'], it[1], it[2], *cfg.VIA) if it[0] == 'V' else B.add_track(q['net'], *it[1:6], it[6]))
        plan.append((q, items))
    if plan is not None:
        found = (x, y, rot, side, plan); break
if not found:
    raise SystemExit('no routable placement found')
x, y, rot, side, plan = found
print('PLACE', a.des, [round(x, 2), round(y, 2), rot, side], {q['id']: cfg.mm(q['shape'].centroid.x, q['shape'].centroid.y, 2) for q, _ in plan})
if a.commit:
    r = eda.run('rip_move.js', 120, {'mv': {a.des: [x, y, rot, side]}})['result']['moved'][a.des]
    got = {f"{a.des}.{n}": (px, py) for n, px, py, _ in r}
    want = {q['id']: cfg.mm(q['shape'].centroid.x, q['shape'].centroid.y, 2) for q, _ in plan}
    if any(math.hypot(got[k][0] - v[0], got[k][1] - v[1]) > 0.05 for k, v in want.items() if k in got):
        if len(mine) != 2:
            raise SystemExit(f'pads landed differently than planned: {got} vs {want}; fix rotation by hand')
        r = eda.run('rip_move.js', 120, {'mv': {a.des: [x, y, (rot + 180) % 360, side]}})['result']['moved'][a.des]
        print('flipped 180 to match plan', r)
    for q, items in plan:
        print('COMMIT', q['id'], eda.commit_items(q['net'], items, a.w).get('success'))
