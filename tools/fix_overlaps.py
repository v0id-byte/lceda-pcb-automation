"""fix_overlaps.py [--only D1,D2] [--skip D3] [--r 3] [--reach 4] [--body] [--max-iter 30] [--dry]

Clear footprint overlaps (courtyard.py) one pair at a time: move the smaller part of the pair (never
U/L/J/CN/Q/F/D) with place_route.py within --r mm, keeping each net's existing track width, rip the
stubs it leaves behind, re-route a net that split, then re-check. Parts with no clean spot are
skipped and reported. Run DRC afterwards; for tiny overlaps try unoverlap.py --drc first."""
import argparse, json, math, os, subprocess, sys
import _boot  # noqa: F401
import cfg, eda  # noqa: E402
PY = sys.executable; T = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument('--only', default=''); ap.add_argument('--skip', default='')
ap.add_argument('--r', type=float, default=3); ap.add_argument('--reach', type=float, default=4); ap.add_argument('--max-iter', type=int, default=30); ap.add_argument('--dry', action='store_true'); ap.add_argument('--body', action='store_true', help='bodies instead of silkscreen outlines')
a = ap.parse_args()
FIXED = ('U', 'L', 'J', 'CN', 'Q', 'F', 'D')   # never move these prefixes
skip = set(filter(None, a.skip.split(','))); only = set(filter(None, a.only.split(',')))

def run(*args, t=1800):
    return subprocess.run([PY, *args], capture_output=True, text=True, timeout=t).stdout


def stubs():
    out = run(os.path.join(T, 'stubs.py'))
    return [l.split() for l in out.splitlines() if l and not l.startswith('dangling')]


def geom():
    return json.load(open(cfg.path('geom.json')))['result']


def area(b):
    return (b[2] - b[0]) * (b[3] - b[1])


KNOWN_STUBS = {s[2] for s in stubs()}
failed = set()
for it in range(a.max_iter):
    out = run(os.path.join(T, 'courtyard.py'), '--json', cfg.path('court_live.json'), *(['--body'] if a.body else []))
    pairs = json.load(open(cfg.path('court_live.json')))['pairs']
    P = {f['d']: f for f in json.load(open(cfg.path('court_live.json')))['parts']}
    todo = []
    for ov, d1, d2, side, at in pairs:
        cand = [d for d in (d1, d2) if not d.startswith(FIXED) and d not in skip and d not in failed and (not only or d in only)]
        if cand:
            todo.append(min(cand, key=lambda d: area(P[d]['box'])))
    if not todo:
        print('nothing movable left;', len(pairs), 'pairs remain'); break
    d = todo[0]
    g = geom(); comp = [c for c in g['comps'] if c['d'] == d][0]
    nets = {p['net'] for p in comp['pads'] if p['net']}
    pads = [(p['x'], p['y']) for p in comp['pads'] if p['net'] and p['net'] != cfg.GND]
    wn = {}
    for t in g['tracks']:
        if t['net'] in nets and t['net'] != cfg.GND and any(math.hypot(t[k1] - x, t[k2] - y) < 40 for x, y in pads for k1, k2 in (('x1', 'y1'), ('x2', 'y2'))):
            wn[t['net']] = max(wn.get(t['net'], 8), t['w'])
    w = max(wn.values(), default=8)
    cx, cy = round((comp['x'] - cfg.OX) / cfg.MIL, 2), round((cfg.OY - comp['y']) / cfg.MIL, 2)
    print(f'[{it}] {d} at {cx},{cy} side {comp["l"]} nets {sorted(nets)} w {w}')
    args = [os.path.join(T, 'place_route.py'), d, '--center', f'{cx},{cy}', '--r', str(a.r), '--sides', str(comp['l']),
            '--step', '0.1', '--reach', str(a.reach), '--w', '8', '--widths', ','.join(f'{k}:{min(v, 25)}' for k, v in wn.items()), '--n', '300'] + (['--body'] if a.body else []) + ([] if a.dry else ['--commit'])
    out = run(*args)
    print('   ', ' | '.join(l for l in out.splitlines() if l.startswith(('PLACE', 'COMMIT', 'flipped', 'no ', 'legal')))[:400])
    if 'PLACE' not in out:
        failed.add(d); continue
    if a.dry:
        failed.add(d); continue
    eda.refresh()
    for _ in range(15):   # rip stubs left on this part's nets
        new = [s for s in stubs() if s[2] not in KNOWN_STUBS and s[0] in nets]
        if not new:
            break
        tid = [t['id'] for t in geom()['tracks'] if t['id'].startswith(new[0][2])][0]
        eda.run('rip_move.js', 60, {'rip': [tid]}); eda.refresh()
    isl = run(os.path.join(T, 'islands.py'), *sorted(nets - {cfg.GND}))
    if 'missing links: 0' not in isl:
        for n in sorted(nets - {cfg.GND}):
            print('    reroute', n, run(os.path.join(T, 'route_net.py'), n, '--w', str(min(wn.get(n, 8), 25)), '--commit', '--all').strip().splitlines()[-1:])
    print('   ', run(os.path.join(T, 'islands.py'), *sorted(nets)).strip().splitlines()[-1])
