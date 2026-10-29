"""route_net.py NET [--w 8] [--clr 6] [--via 12,24] [--layers 1,16,2] [--commit [--all]]

Connect the smallest pad-bearing island of NET to the rest of the net with the grid A* router,
pre-check clearances, and (with --commit) write the copper and refresh the geometry. One island
per run; --all repeats until the net is one island or a route fails (exit 1 no path, 2 conflicts).
"""
import argparse, sys
import _boot  # noqa: F401
import cfg, router, check, eda
from shapely.ops import unary_union

ap = argparse.ArgumentParser()
ap.add_argument('net'); ap.add_argument('--w', type=float, default=8); ap.add_argument('--clr', type=float, default=cfg.CLR)
ap.add_argument('--via', help='hole,dia mil (default: per-net from project.json via.nets)'); ap.add_argument('--layers')
ap.add_argument('--commit', action='store_true'); ap.add_argument('--all', action='store_true', help='with --commit: repeat until one island')
a = ap.parse_args()
V = tuple(float(v) for v in a.via.split(',')) if a.via else cfg.via_for(a.net)
Ls = tuple(int(x) for x in a.layers.split(',')) if a.layers else cfg.ROUTE_LAYERS
def once():
    B = router.Board()
    isl = sorted([i for i in B.islands(a.net) if any(x['kind'] == 'pad' for x in i)], key=len)
    if len(isl) < 2:
        print(a.net, 'already one island'); return 0
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
        return 1
    items = [(r[0], r[1], r[2], r[3], r[4], r[5], a.w) if r[0] == 'T' else r for r in res]
    cf = [c for c in check.conflicts(B, a.net, items, a.clr - 0.02, a.w, V) if c[1] != 'pour']
    fmt = lambda x: (x[0], x[1], *cfg.mm(x[2], x[3], 2), *cfg.mm(x[4], x[5], 2)) if x[0] == 'T' else ('V', *cfg.mm(x[1], x[2], 2))
    print('items (mm):', [fmt(x) for x in items]); print('conflicts', cf[:5])
    if cf:
        return 2
    if not a.commit:
        return 0
    print('COMMIT', eda.commit_items(a.net, items, a.w, V))
    return 3


for _ in range(50 if a.all and a.commit else 1):
    rc = once()
    if rc != 3:
        sys.exit(rc)
    eda.refresh()
sys.exit(0)
