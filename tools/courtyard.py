"""courtyard.py [--gap 0.0] [--body] [--json out.json] : parts whose footprints (pads + silkscreen outline) overlap.

DRC only checks copper. Two parts can pass DRC with their bodies or silkscreen outlines on top of
each other, so the pick-and-place machine cannot fit them. This check uses each footprint's
extent from LCEDA (pads + footprint silkscreen, designator text excluded) as an axis-aligned box.
Parts on the same side must be at least --gap mm apart (0 = outlines may touch, not overlap).
A through-hole part counts on its own side. On the other side only its pads matter, and DRC
already checks those.

--body: compare estimated component bodies instead (lib/bodies.py), for a board that ships without
silkscreen. Bodies must still not touch: the pick-and-place machine needs the space.
"""
import argparse, itertools, json
import _boot  # noqa: F401
import eda, bodies

ap = argparse.ArgumentParser()
ap.add_argument('--gap', type=float, default=0.0, help='required clearance between outlines, mm')
ap.add_argument('--json'); ap.add_argument('--only', help='comma-separated designators to report')
ap.add_argument('--body', action='store_true', help='compare estimated bodies, not silkscreen outlines')
a = ap.parse_args()
r = eda.run('comp_bbox.js', 300)
if not r.get('success'):
    raise SystemExit(f"comp_bbox.js failed: {r.get('error')}")
parts = r['result']
if a.body:
    for p in parts:
        p['box'], p['est'] = bodies.body_box(p)
only = set(a.only.split(',')) if a.only else None
bad = []
for p, q in itertools.combinations(parts, 2):
    if p['layer'] != q['layer']:
        continue
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = p['box'], q['box']
    ox = min(ax1, bx1) - max(ax0, bx0) + a.gap   # > 0: closer than the gap in x
    oy = min(ay1, by1) - max(ay0, by0) + a.gap
    if ox > 1e-3 and oy > 1e-3:
        if only and not ({p['d'], q['d']} & only):
            continue
        bad.append((round(min(ox, oy), 3), p['d'], q['d'], 'top' if p['layer'] == 1 else 'bottom',
                    [round((max(ax0, bx0) + min(ax1, bx1)) / 2, 2), round((max(ay0, by0) + min(ay1, by1)) / 2, 2)]))
bad.sort(reverse=True)
for b in bad:
    print(f'{b[1]:>6} x {b[2]:<6} {b[3]:6} overlap {b[0]:.3f} mm at {b[4]}')
print('overlapping pairs:', len(bad))
if a.json:
    json.dump({'gap': a.gap, 'pairs': bad, 'parts': parts}, open(a.json, 'w'), indent=1)
