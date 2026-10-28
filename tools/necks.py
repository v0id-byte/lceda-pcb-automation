"""necks.py NET:min_mil [NET:min_mil ...] : places where a net's copper (tracks + pours, per layer) is
narrower than min_mil. Pad/pin-limited necks show up too: judge them against the pin pitch."""
import sys
import _boot  # noqa: F401
import cfg, pcbgeo
from shapely.ops import unary_union
g, objs = pcbgeo.load()
for arg in sys.argv[1:]:
    net, thr = arg.rsplit(':', 1); thr = float(thr)
    o = [x for x in objs if x['net'] == net]; pads = [x for x in o if x['kind'] == 'pad']
    for L in pcbgeo.CU:
        sh = [x['shape'].buffer(0.15) for x in o if L in x['layers'] and x['kind'] in ('track', 'pour')]
        if not sh:
            continue
        U = unary_union(sh); r = thr / 2
        thin = U.difference(U.buffer(-r).buffer(r + 0.3))
        for p in getattr(thin, 'geoms', [thin]):
            if p.is_empty or p.area < thr * 4:
                continue
            b = p.bounds
            near = sorted(pads, key=lambda q: q['shape'].distance(p))[:2]
            print(f"{net:12s} L{L:<3d} <{thr:g} mil at {cfg.mm(*p.centroid.coords[0], 2)} span {max(b[2] - b[0], b[3] - b[1]) / cfg.MIL:.2f} mm near {[q['id'] for q in near]}")
