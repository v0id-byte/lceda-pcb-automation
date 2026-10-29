"""route_order.py NET1 NET2 ... [--layers 1,2,16] [--layers2 ...] [--w 8] [--commit]

Greedy single-net routing is order-sensitive: in a dense block the first net routed often walls in the
next one. This tries every order of the given nets (each net: smallest island to the rest, as
route_net.py) in memory, keeps the orders where every net routes, and picks the shortest total.
--layers2 offers a second layer set tried per net when the first fails. --commit writes the winner.
"""
import argparse, itertools, math
import _boot  # noqa: F401
import cfg, router, check, eda
from shapely.ops import unary_union

ap = argparse.ArgumentParser(); ap.add_argument('nets', nargs='+'); ap.add_argument('--layers', default='1,2'); ap.add_argument('--layers2', default='1,2,16')
ap.add_argument('--w', type=float, default=8); ap.add_argument('--maxexp', type=int, default=300000); ap.add_argument('--commit', action='store_true'); ap.add_argument('--rip', action='store_true', help='first remove the existing tracks/vias of these nets (in memory; deleted for real on --commit)'); ap.add_argument('--max-orders', type=int, default=0, help='try a random sample of orders')
a = ap.parse_args()
LS = [tuple(int(x) for x in s.split(',')) for s in (a.layers, a.layers2) if s]


def route_one(B, net):
    out = []
    for _ in range(6):  # join islands one by one
        isl = sorted([i for i in B.islands(net) if any(x['kind'] == 'pad' for x in i)], key=len)
        if len(isl) < 2:
            return out
        src, dst = isl[0], [o for i in isl[1:] for o in i]
        b = unary_union([o['shape'] for o in src + dst]).bounds; res = None
        for Ls in LS:
            for m in (120, 300, 600):
                res, _ = router.route(B, net, src, dst, w=a.w, clr=cfg.CLR + 0.3, window=(b[0] - m, b[1] - m, b[2] + m, b[3] + m), layers=Ls,
                                      via_cost=20, via_thru_pour=tuple(cfg.PLANES), maxexp=a.maxexp)
                if res:
                    break
            if res:
                break
        if not res:
            return None
        items = [(r[0], r[1], r[2], r[3], r[4], r[5], a.w) if r[0] == 'T' else r for r in res]
        if [c for c in check.conflicts(B, net, items, cfg.CLR - 0.02, a.w) if c[1] != 'pour']:
            return None
        for it in items:
            (B.add_via(net, it[1], it[2], *cfg.via_for(net)) if it[0] == 'V' else B.add_track(net, *it[1:6], it[6]))
        out.append(items)
    return out


best = None
orders = list(itertools.permutations(a.nets))
if a.max_orders and len(orders) > a.max_orders:
    import random; random.seed(1); orders = random.sample(orders, a.max_orders)
for order in orders:
    B = router.Board(); plan = []; total = 0; vias = 0
    if a.rip:
        B.remove(lambda o: o['net'] in a.nets and o['kind'] in ('track', 'via'))
    for net in order:
        r = route_one(B, net)
        if r is None:
            plan = None; break
        for items in r:
            plan.append((net, items))
            total += sum(math.hypot(i[4] - i[2], i[5] - i[3]) for i in items if i[0] == 'T') / cfg.MIL
            vias += sum(1 for i in items if i[0] == 'V')
    print(order, 'FAIL' if plan is None else f'{total:.1f} mm, {vias} vias')
    if plan is not None and (best is None or total + 2 * vias < best[0]):
        best = (total + 2 * vias, order, plan)
if not best:
    raise SystemExit('no order routes all nets')
print('BEST', best[1])
if a.commit:
    if a.rip:
        old = [o['id'] for o in router.Board().all_objs() if o['net'] in a.nets and o['kind'] in ('track', 'via')]
        print('rip', len(old), eda.run_code('\n'.join(['await pcb();'] + eda.delete_js(old) + ['return 1;']), 300).get('success'))
    for net, items in best[2]:
        print('COMMIT', net, eda.commit_items(net, items, a.w).get('success'))
