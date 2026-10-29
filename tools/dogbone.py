"""dogbone.py PAD [PAD ...] [--r 1.5] [--dam 0.15] [--commit] : move a via out of an SMD pad.

For every via whose drill hole lands on PAD (e.g. C8.2, see tools/vias_in_pads.py), search the nearest
spot where the hole sits at least --dam mm outside every SMD pad, move the via there, drag the tracks
that ended on it (all layers), and join it back to the pad with a short stub on the pad's layer.
Everything moved or added is clearance-checked before anything is written. Run refresh.py, DRC and
islands.py afterwards.
"""
import argparse, json, math
from collections import Counter
import _boot  # noqa: F401
import cfg, router, check, eda
from shapely.geometry import Point

ap = argparse.ArgumentParser(); ap.add_argument('pads', nargs='+')
ap.add_argument('--r', type=float, default=1.5, help='search radius around the pad, mm')
ap.add_argument('--step', type=float, default=0.05)
ap.add_argument('--dam', type=float, default=0.15, help='min distance from the drill hole to any SMD pad, mm')
ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
B = router.Board(); objs = B.all_objs()
smd = [o for o in objs if o['kind'] == 'pad' and o.get('ref') not in (None, '__SLOT') and len(o['layers']) == 1]
js = ['await pcb();', 'const r=[];']
bad = 0
for pid in a.pads:
    pad = next((o for o in smd if o['id'] == pid), None)
    if not pad:
        raise SystemExit(f'no SMD pad {pid}')
    L = pad['layers'][0]
    for v in [o for o in B.all_objs() if o['kind'] == 'via']:
        hole_r = (v.get('hole') or cfg.VIA[0]) / 2
        if not Point(v['x'], v['y']).buffer(hole_r, 12).intersects(pad['shape']):
            continue
        V = (v.get('hole') or cfg.VIA[0], v['dia'])
        clr = cfg.CLR_STRONG if v['net'] in cfg.STRONG else cfg.CLR
        tr = [t for t in B.all_objs() if t['kind'] == 'track' and t['net'] == v['net']
              and any(math.hypot(t[k1] - v['x'], t[k2] - v['y']) < 0.5 for k1, k2 in (('x1', 'y1'), ('x2', 'y2')))]
        B.remove(lambda o: o is v or any(o is t for t in tr))
        pb = pad['shape'].bounds
        sw = min(10, 0.8 * min(pb[2] - pb[0], pb[3] - pb[1]))   # stub width, mil
        dam = hole_r + a.dam * cfg.MIL
        n = int(a.r / a.step)
        cands = sorted(((i * a.step, j * a.step) for i in range(-n, n + 1) for j in range(-n, n + 1)
                        if math.hypot(i, j) <= n), key=lambda d: math.hypot(*d))
        cx, cy = pad['x'], pad['y']
        best, why = None, Counter()   # why: rejection reasons, printed when nothing fits
        for dx, dy in cands:
            nx, ny = cx + dx * cfg.MIL, cy - dy * cfg.MIL
            P = Point(nx, ny)
            if any(P.distance(o['shape']) < dam for o in smd):
                why['too close to a pad'] += 1; continue
            moved = []
            for t in tr:
                c = [t['x1'], t['y1'], t['x2'], t['y2']]
                for k in (0, 2):
                    if math.hypot(c[k] - v['x'], c[k + 1] - v['y']) < 0.5:
                        c[k], c[k + 1] = nx, ny
                moved.append((t, c))
            items = [('V', nx, ny), ('T', L, cx, cy, nx, ny, sw)] + [('T', t['layers'][0], *c, t['w']) for t, c in moved]
            cf = [c for c in check.conflicts(B, v['net'], items, clr - 0.02, 8, V, via_thru_pour=tuple(cfg.PLANES)) if c[1] != 'pour']
            why.update(f'{c[1]} {c[3]} {str(c[2])[:8]}' for c in cf)
            if not cf:
                best = (nx, ny, moved, sw); break
        if not best:
            print(pid, v['net'], 'via', v['id'][:10], f'no legal spot within {a.r} mm; blocked by', why.most_common(4)); bad += 1
            B.objs.append(v); B.objs.extend(tr); continue
        nx, ny, moved, sw = best
        print(pid, v['net'], 'via', v['id'][:10], cfg.mm(v['x'], v['y'], 2), '->', cfg.mm(nx, ny, 2),
              f'stub {math.hypot(nx - cx, ny - cy) / cfg.MIL:.2f} mm w {sw:.1f} mil, {len(moved)} tracks dragged')
        B.add_via(v['net'], nx, ny, *V); B.add_track(v['net'], L, cx, cy, nx, ny, sw)
        for t, c in moved:
            B.add_track(v['net'], t['layers'][0], *c, t['w'])
        n_ = json.dumps(v['net'])
        js += [f'await eda.pcb_PrimitiveVia.delete([{json.dumps(v["id"])}]);',
               f'r.push((await eda.pcb_PrimitiveVia.create({n_},{nx:.4f},{ny:.4f},{V[0]},{V[1]})).primitiveId);',
               f'r.push((await eda.pcb_PrimitiveLine.create({n_},{L},{cx:.4f},{cy:.4f},{nx:.4f},{ny:.4f},{sw:.2f})).primitiveId);']
        for t, c in moved:
            js += [f'await eda.pcb_PrimitiveLine.delete([{json.dumps(t["id"])}]);',
                   f'r.push((await eda.pcb_PrimitiveLine.create({n_},{t["layers"][0]},{c[0]:.4f},{c[1]:.4f},{c[2]:.4f},{c[3]:.4f},{t["w"]})).primitiveId);']
if a.commit and not bad:
    js.append('return r;')
    print('COMMIT', eda.run_code('\n'.join(js), 200))
elif a.commit:
    print('not committed:', bad, 'via(s) without a legal spot')
