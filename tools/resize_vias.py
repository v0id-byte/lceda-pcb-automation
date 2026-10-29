"""resize_vias.py [--min-hole 0.3] [--hole 0.3048] [--dia 0.5,0.45] [--r 0.5] [--commit] : bring small vias up to the fab's standard size.

Fabs charge extra for vias below their standard drill (JLC: hole < 0.3 mm or diameter <= 0.4 mm means
TG155 material, four-wire via testing and a small-hole fee). Every via with a hole under --min-hole is
re-made at --hole / the first --dia that fits: in place if it can, otherwise at the nearest spot within
--r mm, dragging the tracks that end on it. A via that touches a pad is only resized in place (moving it
would leave the pad). Everything is clearance-checked first. A moved via is deleted and re-created; check DRC
for teardrops it leaves behind (delete the orphan by the id DRC reports). Run refresh.py --rebuild, DRC and islands.py after.
"""
import argparse, json, math
import _boot  # noqa: F401
import cfg, router, check, eda
from shapely.geometry import Point

ap = argparse.ArgumentParser()
ap.add_argument('--min-hole', type=float, default=0.3); ap.add_argument('--hole', type=float, default=0.3048, help='12 mil: LCEDA stores mil with one decimal, so 0.3 mm would come back as 11.8 mil = 0.2997 mm')
ap.add_argument('--dia', default='0.5,0.45', help='outer diameters to try, mm, preferred first')
ap.add_argument('--r', type=float, default=0.5, help='search radius when it does not fit in place, mm')
ap.add_argument('--step', type=float, default=0.05); ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
H = a.hole * cfg.MIL; DIAS = [float(d) * cfg.MIL for d in a.dia.split(',')]
B = router.Board()
small = [o for o in B.all_objs() if o['kind'] == 'via' and (o.get('hole') or 0) < a.min_hole * cfg.MIL]
pads = [o for o in B.all_objs() if o['kind'] == 'pad']
n = int(a.r / a.step)
spots = sorted(((i * a.step, j * a.step) for i in range(-n, n + 1) for j in range(-n, n + 1) if i * i + j * j <= n * n),
               key=lambda d: math.hypot(*d))
js = ['await pcb();', 'const r=[];']; bad = []
for v in small:
    tr = [t for t in B.all_objs() if t['kind'] == 'track' and t['net'] == v['net']
          and any(math.hypot(t[k1] - v['x'], t[k2] - v['y']) < 0.5 for k1, k2 in (('x1', 'y1'), ('x2', 'y2')))]
    on_pad = any(p['net'] == v['net'] and p['shape'].intersects(v['shape']) for p in pads)
    B.remove(lambda o: o is v or any(o is t for t in tr))
    clr = cfg.CLR_STRONG if v['net'] in cfg.STRONG else cfg.CLR
    done = None
    for dia in DIAS:
        for dx, dy in (spots[:1] if on_pad else spots):
            nx, ny = v['x'] + dx * cfg.MIL, v['y'] - dy * cfg.MIL
            moved = []
            for t in tr:
                c = [t['x1'], t['y1'], t['x2'], t['y2']]
                for k in (0, 2):
                    if math.hypot(c[k] - v['x'], c[k + 1] - v['y']) < 0.5:
                        c[k], c[k + 1] = nx, ny
                moved.append((t, c))
            hole = Point(nx, ny).buffer(H / 2, 12)
            if not on_pad and any(p['shape'].intersects(hole) for p in pads if len(p['layers']) == 1):
                continue   # do not create a new via-in-pad
            items = [('V', nx, ny)] + [('T', t['layers'][0], *c, t['w']) for t, c in moved]
            cf = [c for c in check.conflicts(B, v['net'], items, clr - 0.02, 8, (H, dia), via_thru_pour=tuple(cfg.PLANES)) if c[1] != 'pour']
            if not cf:
                done = (nx, ny, dia, moved); break
        if done:
            break
    xy = cfg.mm(v['x'], v['y'], 2)
    if not done:
        print(v['net'], xy, 'no fit'); bad.append(v); B.objs.append(v); B.objs.extend(tr); continue
    nx, ny, dia, moved = done
    print(v['net'], xy, '->', cfg.mm(nx, ny, 2), f'{a.hole}/{dia / cfg.MIL:.2f} mm', 'in place' if (nx, ny) == (v['x'], v['y']) else f'moved {math.hypot(nx - v["x"], ny - v["y"]) / cfg.MIL:.2f} mm', f'{len(moved)} tracks')
    B.add_via(v['net'], nx, ny, H, dia)
    for t, c in moved:
        B.add_track(v['net'], t['layers'][0], *c, t['w'])
    nn = json.dumps(v['net'])
    if (nx, ny) == (v['x'], v['y']):   # in place: modify, so its teardrops stay attached (delete + create orphans them)
        js.append(f'await eda.pcb_PrimitiveVia.modify({json.dumps(v["id"])}, {{holeDiameter: {H:.4f}, diameter: {dia:.4f}}}); r.push({json.dumps(v["id"])});')
    else:
        js += [f'await eda.pcb_PrimitiveVia.delete([{json.dumps(v["id"])}]);',
               f'r.push((await eda.pcb_PrimitiveVia.create({nn},{nx:.4f},{ny:.4f},{H:.4f},{dia:.4f})).primitiveId);']
    for t, c in moved:
        if (c[0], c[1], c[2], c[3]) != (t['x1'], t['y1'], t['x2'], t['y2']):
            js += [f'await eda.pcb_PrimitiveLine.delete([{json.dumps(t["id"])}]);',
                   f'r.push((await eda.pcb_PrimitiveLine.create({nn},{t["layers"][0]},{c[0]:.4f},{c[1]:.4f},{c[2]:.4f},{c[3]:.4f},{t["w"]})).primitiveId);']
print(f'{len(small) - len(bad)}/{len(small)} vias fit')
if a.commit:
    js.append('return r;')
    print('COMMIT', eda.run_code('\n'.join(js), 200))
