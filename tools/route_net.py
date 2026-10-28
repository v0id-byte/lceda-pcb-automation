"""route_net.py NET [--w 8] [--clr 6] [--via 12,24] [--layers 1,16,2] [--commit]

Connect the smallest pad-bearing island of NET to the rest of the net with the grid A* router,
pre-check clearances, and (with --commit) write the copper. Repeat (refresh in between) until the
net has one island:  for i in 1 2 3; do route_net.py X --commit && refresh.py; done
"""
import argparse, sys
import _boot  # noqa: F401
import cfg, router, check, eda
from shapely.ops import unary_union

ap = argparse.ArgumentParser()
ap.add_argument('net'); ap.add_argument('--w', type=float, default=8); ap.add_argument('--clr', type=float, default=cfg.CLR)
ap.add_argument('--via', default=','.join(map(str, cfg.VIA))); ap.add_argument('--layers')
ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
V = tuple(float(v) for v in a.via.split(','))
Ls = tuple(int(x) for x in a.layers.split(',')) if a.layers else cfg.ROUTE_LAYERS
B = router.Board()
isl = sorted([i for i in B.islands(a.net) if any(x['kind'] == 'pad' for x in i)], key=len)
if len(isl) < 2:
    print(a.net, 'already one island'); sys.exit(0)
src, dst = isl[0], [o for i in isl[1:] for o in i]
b = unary_union([o['shape'] for o in src + dst]).bounds
strong = a.net in cfg.STRONG
res = None
for m in (80, 200, 500):  # grow the search window
    res, msg = router.route(B, a.net, src, dst, w=a.w, clr=a.clr + 0.3, window=(b[0] - m, b[1] - m, b[2] + m, b[3] + m),
                            layers=Ls, via=V, via_cost=20, maxexp=3_000_000, via_thru_pour=tuple(cfg.PLANES),
                            clr_track=(cfg.CLR_STRONG + 0.3 if strong else None))
    print(a.net, [x['id'] for x in src if x['kind'] == 'pad'][:6], 'margin', m, msg)
    if res:
        break
if not res:
    sys.exit(1)
items = [(r[0], r[1], r[2], r[3], r[4], r[5], a.w) if r[0] == 'T' else r for r in res]
cf = [c for c in check.conflicts(B, a.net, items, a.clr - 0.02, a.w, V) if c[1] != 'pour']
fmt = lambda x: (x[0], x[1], *cfg.mm(x[2], x[3], 2), *cfg.mm(x[4], x[5], 2)) if x[0] == 'T' else ('V', *cfg.mm(x[1], x[2], 2))
print('items (mm):', [fmt(x) for x in items]); print('conflicts', cf[:5])
if cf:
    sys.exit(2)
if a.commit:
    print('COMMIT', eda.commit_items(a.net, items, a.w, V))
