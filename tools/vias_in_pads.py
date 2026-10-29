"""vias_in_pads.py [--skip U1,U10] [--geom geom.json] [--json out.json] : vias whose drill hole lands on an SMD pad.

A drill hole inside an SMD pad wicks solder down the barrel during reflow (a starved or tilted joint)
unless the fab fills and caps it (resin plugging + plating, extra cost). DRC does not flag it: the via
and the pad share a net. Run after refresh.py. Thermal pads that are meant to carry via arrays go in
--skip. 'ring' rows (only the annular ring touches the pad) are harmless; 'HOLE' rows need fixing or a
via-in-pad note on the order.
"""
import argparse, json
import _boot  # noqa: F401
import cfg, pcbgeo
from shapely.geometry import Point

ap = argparse.ArgumentParser()
ap.add_argument('--skip', default='', help='comma-separated designators whose pads may carry vias')
ap.add_argument('--geom', help='an older geom.json (e.g. a snapshot) instead of the live one, to diff against')
ap.add_argument('--json')
a = ap.parse_args()
skip = set(filter(None, a.skip.split(',')))
g, objs = pcbgeo.load(a.geom)
pads = [o for o in objs if o['kind'] == 'pad' and o.get('ref') not in (None, '__SLOT') and o['ref'] not in skip
        and len(o['layers']) == 1]   # SMD only; through-hole pads are holes already
vias = [o for o in objs if o['kind'] == 'via']
rows = []
for v in vias:
    hole = Point(v['x'], v['y']).buffer((v.get('hole') or v['dia'] / 2) / 2, 12)
    for p in pads:
        if not v['shape'].intersects(p['shape']):
            continue
        kind = 'HOLE' if hole.intersects(p['shape']) else 'ring'
        mx, my = (v['x'] - cfg.OX) / cfg.MIL, (cfg.OY - v['y']) / cfg.MIL
        rows.append((kind, p['id'], p['net'], v['id'], round(mx, 2), round(my, 2), round(v['dia'] / cfg.MIL, 2)))
rows.sort()
for r in rows:
    print(f'{r[0]:4} {r[1]:>8} {r[2]:<12} via {r[3][:10]} at ({r[4]}, {r[5]}) dia {r[6]} mm')
print('vias with the hole in a pad:', sum(r[0] == 'HOLE' for r in rows))
if a.json:
    json.dump(rows, open(a.json, 'w'), indent=1)
