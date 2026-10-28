"""gnd_fix.py PAD [PAD ...] [--net GND] [--commit]

Reconnect ground pads/islands that the pour left floating (typical after a pour rebuild).
For each pad: 1) look for the nearest legal via spot (<= 4 mm) that lands INSIDE the main plane island
on a plane layer and add a short track + via; 2) otherwise run the router from the pad's island to any
main-island pour. Then refresh with --rebuild and re-run DRC.
If neither works the island is usually a pocket enclosed by signal tracks on the plane layers:
look at it with render.py --islands GND and move one of the enclosing tracks.
"""
import argparse, math
import _boot  # noqa: F401
import cfg, router, check, pcbgeo, eda
from shapely.geometry import Point, box
from shapely.ops import unary_union

ap = argparse.ArgumentParser(); ap.add_argument('pads', nargs='+'); ap.add_argument('--net', default=cfg.GND)
ap.add_argument('--w', type=float, default=10); ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
B = router.Board(); V = cfg.VIA
isl = B.islands(a.net); MAIN = max(isl, key=len)
planes = cfg.PLANES or cfg.CU
MP = unary_union([o['shape'] for o in MAIN if o['kind'] == 'pour' and o['layers'][0] in planes])
for pid in a.pads:
    p = [o for o in B.all_objs() if o['id'] == pid][0]
    if any(o is p for o in MAIN):
        print(pid, 'already on the main island (if DRC still flags it, the track/via ends do not land on it exactly)')
        continue
    L =p['layers'][0] if len(p['layers']) == 1 else cfg.CU[-1]
    cx, cy = p['shape'].centroid.x, p['shape'].centroid.y
    best = None
    for rr in [x * 2.5 for x in range(8, 64)]:
        for k in range(24):
            vx, vy = cx + rr * math.cos(k * math.pi / 12), cy + rr * math.sin(k * math.pi / 12)
            if not MP.contains(Point(vx, vy).buffer(V[1] / 2 + 2)):
                continue
            items = [('V', vx, vy), ('T', L, cx, cy, vx, vy, a.w)]
            if not [c for c in check.conflicts(B, a.net, items, cfg.CLR, a.w, V) if c[1] != 'pour']:
                best = items; break
        if best:
            break
    if not best:  # route the whole island to the main plane
        src = [o for i in isl if any(x['id'] == pid for x in i) for o in i if o['kind'] != 'pour']
        bx = src[0]['shape'].bounds; m = 160; win = (bx[0] - m, bx[1] - m, bx[2] + m, bx[3] + m); W = box(*win)
        dst = [dict(o, shape=o['shape'].intersection(W.buffer(-20))) for o in MAIN if o['kind'] == 'pour' and o['shape'].intersects(W)]
        dst = [o for o in dst if not o['shape'].is_empty and o['shape'].area > 1]
        res, msg = router.route(B, a.net, src, dst, w=a.w - 2, clr=cfg.CLR + 0.2, window=win, layers=tuple(cfg.CU),
                                layer_cost={L_: (4 if L_ in cfg.PLANES else 1) for L_ in cfg.CU}, via_cost=15,
                                via_thru_pour=tuple(cfg.PLANES))
        if not res:
            print(pid, 'NOFIT', msg); continue
        best = [(r[0], r[1], r[2], r[3], r[4], r[5], a.w - 2) if r[0] == 'T' else r for r in res]
    for it in best:
        (B.add_via(a.net, it[1], it[2], *V) if it[0] == 'V' else B.add_track(a.net, *it[1:6], it[6]))
    print(pid, [(x[0], *(cfg.mm(x[1], x[2], 2) if x[0] == 'V' else cfg.mm(x[2], x[3], 2) + cfg.mm(x[4], x[5], 2))) for x in best])
    if a.commit:
        print(' COMMIT', eda.commit_items(a.net, best, a.w, V))
