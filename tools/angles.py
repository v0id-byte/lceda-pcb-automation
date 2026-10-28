"""angles.py : track corners of 90 deg or sharper that are not inside a pad/via (acid traps, ugly bends).
Acute (<89 deg) ones are worth fixing; tiny zig-zag stubs are the usual cause."""
import json, math, collections
import _boot  # noqa: F401
import cfg
g = json.load(open(cfg.path('geom.json')))['result']
K = lambda x, y: (round(x, 1), round(y, 1))
vias = {K(v['x'], v['y']) for v in g['vias']}
pads = []
for c in g['comps']:
    for p in c['pads']:
        sz = [v for v in (p['pad'] or [])[1:3] if isinstance(v, (int, float))] or [10]
        pads.append((p['x'], p['y'], max(sz) / 2, p['l'], p['hole']))
onpad = lambda x, y, L: any((hole or l == L) and abs(x - px) <= r and abs(y - py) <= r for px, py, r, l, hole in pads)
ends = collections.defaultdict(list)
for t in g['tracks']:
    if math.hypot(t['x2'] - t['x1'], t['y2'] - t['y1']) < 0.05:
        continue
    ends[(t['net'], t['l'], K(t['x1'], t['y1']))].append((t, (t['x2'] - t['x1'], t['y2'] - t['y1'])))
    ends[(t['net'], t['l'], K(t['x2'], t['y2']))].append((t, (t['x1'] - t['x2'], t['y1'] - t['y2'])))
bad = []
for (net, L, pt), lst in ends.items():
    if len(lst) != 2 or pt in vias:
        continue
    (t1, u), (t2, v) = lst
    lu, lv = math.hypot(*u), math.hypot(*v)
    ang = math.degrees(math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))))
    if ang <= 91 and not onpad(pt[0], pt[1], L):
        bad.append((round(ang, 1), net, L, cfg.mm(*pt), t1['id'], t2['id'], round(lu / cfg.MIL, 2), round(lv / cfg.MIL, 2)))
bad.sort()
print('corners <= 91 deg:', len(bad), ' acute (<89):', sum(1 for b in bad if b[0] < 89))
print(collections.Counter(b[1] for b in bad).most_common(20))
for b in bad:
    print(b)
