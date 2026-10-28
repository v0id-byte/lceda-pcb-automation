"""islands.py [NET ...] : nets whose pads are split into several copper islands (geometric pre-check).
No argument = every net. DRC's "Connection Error" list is the authority; use this to find WHY."""
import sys
import _boot  # noqa: F401
import cfg, pcbgeo
g, objs = pcbgeo.load()
nets = sys.argv[1:] or sorted({o['net'] for o in objs if o['net'] and o['kind'] == 'pad' and o['net'] != '__SLOT'})
tot = 0
for n in nets:
    isl = [i for i in pcbgeo.islands(objs, n) if any(x['kind'] == 'pad' for x in i)]
    if len(isl) > 1:
        tot += len(isl) - 1
        print(f"{n:20s} {len(isl) - 1:3d} | " + ' || '.join(','.join(x['id'] for x in i if x['kind'] == 'pad')[:60] for i in isl[1:])[:240])
print('TOTAL missing links:', tot)
