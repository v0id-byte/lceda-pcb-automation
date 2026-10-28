"""route_zone.py NET x0,y0,x1,y1(mm) [--w 8] [--clr 6] [--layers 2,1,16] [--commit]

Join the islands of NET that have pads inside the zone, searching only inside the zone. Every island
is tried as the source in turn (a boxed-in pad often routes out but not in). Good for dense areas.
"""
import argparse, sys
import _boot  # noqa: F401
import cfg, router, check, eda

ap = argparse.ArgumentParser()
ap.add_argument('net'); ap.add_argument('zone'); ap.add_argument('--w', type=float, default=8)
ap.add_argument('--clr', type=float, default=cfg.CLR); ap.add_argument('--layers'); ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
Z = cfg.box_mm(*map(float, a.zone.split(',')))
Ls = tuple(int(x) for x in a.layers.split(',')) if a.layers else cfg.ROUTE_LAYERS
B = router.Board()
isl = sorted([i for i in B.islands(a.net) if any(x['kind'] == 'pad' and Z.contains(x['shape'].centroid) for x in i)], key=len)
print('zone islands', len(isl), [[x['id'] for x in i if x['kind'] == 'pad'][:4] for i in isl])
if len(isl) < 2:
    sys.exit(0)
res = None
for k in range(len(isl)):
    src = isl[k]; dst = [o for j, i in enumerate(isl) if j != k for o in i]
    res, msg = router.route(B, a.net, src, dst, w=a.w, clr=a.clr + 0.3, window=Z.bounds, layers=Ls, via_cost=20,
                            via_thru_pour=tuple(cfg.PLANES))
    print([x['id'] for x in src if x['kind'] == 'pad'][:3], msg)
    if res:
        break
if not res:
    sys.exit(1)
items = [(r[0], r[1], r[2], r[3], r[4], r[5], a.w) if r[0] == 'T' else r for r in res]
cf = [c for c in check.conflicts(B, a.net, items, a.clr - 0.02, a.w) if c[1] != 'pour']
print('conflicts', cf[:5])
if cf:
    sys.exit(2)
if a.commit:
    print('COMMIT', eda.commit_items(a.net, items, a.w))
