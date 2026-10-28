"""stubs.py : track ends that touch nothing of their own net (dangling stubs / antennas left by rips)."""
import _boot  # noqa: F401
import cfg, pcbgeo
from shapely.geometry import Point
from shapely.strtree import STRtree
g, objs = pcbgeo.load()
cu = [o for o in objs if o['kind'] in ('pad', 'via', 'track', 'pour')]
tree = STRtree([o['shape'] for o in cu])
n = 0
for t in [o for o in objs if o['kind'] == 'track']:
    for x, y in ((t['x1'], t['y1']), (t['x2'], t['y2'])):
        p = Point(x, y).buffer(0.5)
        hit = [cu[int(i)] for i in tree.query(p)]
        hit = [o for o in hit if o is not t and o['net'] == t['net'] and set(o['layers']) & set(t['layers']) and o['shape'].intersects(p)]
        if not hit:
            n += 1
            print(f"{t['net']:14s} L{t['layers'][0]:<3d} {t['id'][:10]} end {cfg.mm(x, y, 2)}")
print('dangling ends:', n)
