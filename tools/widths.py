"""widths.py [NET ...] : track width histogram per net (mil). No argument = nets with any track >= 15 mil.
Compare with the rule table and the current each net carries; necks inside pours: see necks.py."""
import sys, collections
import _boot  # noqa: F401
import pcbgeo
g, objs = pcbgeo.load()
W = collections.defaultdict(list)
for o in objs:
    if o['kind'] == 'track':
        W[o['net']].append(round(o['w'], 1))
nets = sys.argv[1:] or sorted(n for n, v in W.items() if max(v) >= 15)
for n in nets:
    v = W.get(n)
    print(f"{n:16s} " + (f"min {min(v):5} max {max(v):5} n={len(v):4d} " + str(sorted(collections.Counter(v).items())) if v else 'no tracks (pour/pads only)'))
