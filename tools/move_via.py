"""move_via.py x,y dx,dy [x,y dx,dy ...] [--commit]   (board mm)

Move vias (found at x,y within 0.05 mm) by dx,dy and drag the end points of every track that ends on
them, on all layers. All moved copper is clearance-checked first. Typical use: nudge signal vias out
of a power corridor so the power track can be widened.
"""
import argparse, json, math
import _boot  # noqa: F401
import cfg, router, check, eda

ap = argparse.ArgumentParser(); ap.add_argument('moves', nargs='+'); ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
pairs = list(zip(a.moves[0::2], a.moves[1::2]))
B = router.Board(); objs = B.all_objs()
plan = []  # (via obj, new x, new y, [(track obj, new coords)])
for p, d in pairs:
    x, y = map(float, p.split(',')); dx, dy = map(float, d.split(','))
    X, Y = cfg.X(x), cfg.Y(y)
    v = min((o for o in objs if o['kind'] == 'via'), key=lambda o: math.hypot(o['x'] - X, o['y'] - Y))
    if math.hypot(v['x'] - X, v['y'] - Y) > 0.05 * cfg.MIL:
        raise SystemExit(f'no via at {p}')
    nx, ny = v['x'] + dx * cfg.MIL, v['y'] - dy * cfg.MIL
    tr = []
    for t in objs:
        if t['kind'] != 'track' or t['net'] != v['net']:
            continue
        c = [t['x1'], t['y1'], t['x2'], t['y2']]
        hit = False
        for k in (0, 2):
            if math.hypot(c[k] - v['x'], c[k + 1] - v['y']) < 0.5:
                c[k], c[k + 1] = nx, ny; hit = True
        if hit:
            tr.append((t, c))
    plan.append((v, nx, ny, tr))
ids = {v['id'] for v, *_ in plan} | {t['id'] for *_, tr in plan for t, _ in tr}
B.remove(lambda o: o['id'] in ids)
bad = 0
for v, nx, ny, tr in plan:
    clr = cfg.CLR_STRONG if v['net'] in cfg.STRONG else cfg.CLR
    V = (v.get('hole') or cfg.VIA[0], v['dia'])
    items = [('V', nx, ny)] + [('T', t['layers'][0], *c, t['w']) for t, c in tr]
    cf = [c for c in check.conflicts(B, v['net'], items, clr - 0.02, 8, V, via_thru_pour=tuple(cfg.PLANES)) if c[1] != 'pour']
    print(v['net'], cfg.mm(v['x'], v['y'], 2), '->', cfg.mm(nx, ny, 2), f'{len(tr)} tracks', 'CONFLICT ' + str(cf[:3]) if cf else 'ok')
    bad += bool(cf)
    B.add_via(v['net'], nx, ny, *V)
    for t, c in tr:
        B.add_track(v['net'], t['layers'][0], *c, t['w'])
if a.commit and not bad:
    js = ['await pcb();', 'const r=[];']
    for v, nx, ny, tr in plan:
        V = (v.get('hole') or cfg.VIA[0], v['dia'])
        js += [f'await eda.pcb_PrimitiveVia.delete([{json.dumps(v["id"])}]);',
               f'r.push((await eda.pcb_PrimitiveVia.create({json.dumps(v["net"])},{nx:.4f},{ny:.4f},{V[0]},{V[1]})).primitiveId);']
        for t, c in tr:
            js += [f'await eda.pcb_PrimitiveLine.delete([{json.dumps(t["id"])}]);',
                   f'r.push((await eda.pcb_PrimitiveLine.create({json.dumps(t["net"])},{t["layers"][0]},{c[0]:.4f},{c[1]:.4f},{c[2]:.4f},{c[3]:.4f},{t["w"]})).primitiveId);']
    js.append('return r;')
    print('COMMIT', eda.run_code('\n'.join(js), 200))
