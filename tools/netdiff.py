"""netdiff.py A.json B.json [NET ...]

Compare two netlists exported by netlist_sch.js / netlist_pcb.js (or any two snapshots):
added/removed parts, every pin whose net changed, the members of the listed nets, single-pin nets.
Schematic vs PCB must print no changes; before/after an edit must print exactly the intended ones."""
import json, sys


def load(f):
    r = json.load(open(f))['result']
    t = json.loads(r['text'] if isinstance(r, dict) else r)
    return {c['props'].get('Designator'): c for c in t['components'].values() if isinstance(c, dict) and 'props' in c}


a, b = load(sys.argv[1]), load(sys.argv[2])
pn = lambda c: {k: i.get('net') for k, i in c['pinInfoMap'].items()}
print('parts', len(a), '->', len(b), ' added', sorted(set(b) - set(a)), ' removed', sorted(set(a) - set(b)))
for d in sorted(set(a) & set(b)):
    if pn(a[d]) != pn(b[d]):
        print(' changed', d, {k: (pn(a[d]).get(k), v) for k, v in pn(b[d]).items() if pn(a[d]).get(k) != v})
nets = {}
for d, c in b.items():
    for k, v in pn(c).items():
        nets.setdefault(v, []).append(f'{d}.{k}')
for n in sys.argv[3:]:
    print(' ', n, nets.get(n))
print(' single-pin nets', [n for n, v in nets.items() if n and len(v) == 1])
