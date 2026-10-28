"""manual.py plan.json [--commit]

Hand-drawn copper with a clearance pre-check. Coordinates in board mm (y down).
plan = {"delete": [track/via ids],
        "items": [{"net": "N", "T": [layer, [[x,y], [x,y], ...], width_mil]},
                  {"net": "N", "V": [x, y], "via": [hole, dia]}],
        "force": false}   # force=true commits despite conflicts (only after you proved them false)
Tip: end every segment exactly on a pad centre, a via centre or another segment's END point. LCEDA's
DRC does not connect a track end that stops in the middle of another segment (or of a via it passes).
"""
import argparse, json
import _boot  # noqa: F401
import cfg, router, check, eda

ap = argparse.ArgumentParser(); ap.add_argument('plan'); ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
P = json.load(open(a.plan))
B = router.Board()
rip = set(P.get('delete', []))
B.remove(lambda o: o['id'] in rip)
js = ['await pcb();'] + (eda.delete_js(rip) if rip else []) + ['const r=[];']
bad = 0
for it in P['items']:
    net = it['net']; clr = it.get('clr', cfg.CLR_STRONG if net in cfg.STRONG else cfg.CLR)
    if 'T' in it:
        L, pts, w = it['T']
        for p, q in zip(pts, pts[1:]):
            x1, y1, x2, y2 = cfg.X(p[0]), cfg.Y(p[1]), cfg.X(q[0]), cfg.Y(q[1])
            cf = [c for c in check.conflicts(B, net, [('T', L, x1, y1, x2, y2, w)], clr - 0.02, w) if c[1] != 'pour']
            if cf:
                bad += 1; print('CONFLICT', net, p, q, cf[:3])
            B.add_track(net, L, x1, y1, x2, y2, w)
            js += eda.items_js(net, [('T', L, x1, y1, x2, y2, w)], w)[2:-1]
    else:
        x, y = cfg.X(it['V'][0]), cfg.Y(it['V'][1]); V = tuple(it.get('via', cfg.VIA))
        cf = [c for c in check.conflicts(B, net, [('V', x, y)], clr - 0.02, 0, V) if c[1] != 'pour']
        if cf:
            bad += 1; print('CONFLICT via', net, it['V'], cf[:3])
        B.add_via(net, x, y, *V)
        js += eda.items_js(net, [('V', x, y)], 0, V)[2:-1]
js.append('return r;')
print('conflicts', bad)
if a.commit and (bad == 0 or P.get('force')):
    print('COMMIT', eda.run_code('\n'.join(js), 200))
