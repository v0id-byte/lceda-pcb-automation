"""move_part.py DESIGNATOR dx,dy (mm) [--commit]

Translate a placed part and drag the end points of every track that ends inside one of its pads, so
the connections survive. Everything moved is clearance-checked first (pads included). For bigger moves
rip and re-route instead.
"""
import argparse, json
import _boot  # noqa: F401
import cfg, router, check, eda
from shapely import affinity
from shapely.geometry import Point

ap = argparse.ArgumentParser(); ap.add_argument('des'); ap.add_argument('d'); ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
dx, dy = map(float, a.d.split(',')); DX, DY = dx * cfg.MIL, -dy * cfg.MIL
B = router.Board(); objs = B.all_objs()
pads = [o for o in objs if o['kind'] == 'pad' and o.get('ref') == a.des]
moved = []
for t in [o for o in objs if o['kind'] == 'track']:
    c = [t['x1'], t['y1'], t['x2'], t['y2']]; hit = False
    for k in (0, 2):
        for p in pads:
            if p['net'] == t['net'] and t['layers'][0] in p['layers'] and p['shape'].contains(Point(c[k], c[k + 1])):
                c[k] += DX; c[k + 1] += DY; hit = True; break
    if hit:
        moved.append((t, c))
ids = {p['id'] for p in pads} | {t['id'] for t, _ in moved}
B.remove(lambda o: o['id'] in ids)
bad = 0
for p in pads:
    s = affinity.translate(p['shape'], DX, DY)
    cf = [o for o in B.all_objs() if o['net'] != p['net'] and o['kind'] != 'pour' and set(o['layers']) & set(p['layers'])
          and o['shape'].distance(s) < router.pclr(cfg.CLR, o['net']) - 0.02]
    if cf:
        bad += 1; print('PAD', p['id'], [(o['kind'], o['net'], round(o['shape'].distance(s), 2)) for o in cf[:3]])
    B.objs.append(dict(p, shape=s))
for t, c in moved:
    clr = cfg.CLR_STRONG if t['net'] in cfg.STRONG else cfg.CLR
    cf = [x for x in check.conflicts(B, t['net'], [('T', t['layers'][0], *c, t['w'])], clr - 0.02, t['w']) if x[1] != 'pour']
    if cf:
        bad += 1; print('TRACK', t['net'], [x[1:4] + (x[5],) for x in cf[:3]])
print(a.des, 'pads', len(pads), 'tracks dragged', len(moved), 'conflicts', bad)
if a.commit and not bad:
    c0 = [x for x in B.g['comps'] if x['d'] == a.des][0]
    js = ['await pcb();', f'const C=eda.pcb_PrimitiveComponent; await C.modify({json.dumps(c0["id"])},{{x:{c0["x"] + DX:.4f},y:{c0["y"] + DY:.4f}}});', 'const r=[];']
    for t, c in moved:
        js += [f'await eda.pcb_PrimitiveLine.delete([{json.dumps(t["id"])}]);',
               f'r.push((await eda.pcb_PrimitiveLine.create({json.dumps(t["net"])},{t["layers"][0]},{c[0]:.4f},{c[1]:.4f},{c[2]:.4f},{c[3]:.4f},{t["w"]})).primitiveId);']
    js.append('return r;')
    print('COMMIT', eda.run_code('\n'.join(js), 200))
