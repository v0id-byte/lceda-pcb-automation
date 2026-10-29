"""unoverlap.py DES [DES ...] [--max 1.5] [--step 0.05] [--gap 0.05] [--tries 60] [--commit | --drc [--drc-tries 6]]

For each part: the smallest translation that clears its footprint outline (pads + silkscreen, as in
courtyard.py) from every part on the same side by --gap mm, stays inside the board, and passes
move_part.py's copper check (attached track ends are dragged along). With --commit it is applied and
the geometry refreshed, so the next part sees the new state. Move small passives, not ICs.

--drc: move_part's copper check uses one clearance for everything and can be stricter than the board's
rule matrix. In this mode each footprint-clear candidate is committed and judged by LCEDA's DRC
instead; a candidate that adds DRC errors is moved back. Start from a DRC-clean board.
"""
import argparse, math, os, subprocess, sys
import _boot  # noqa: F401
import cfg, eda, bodies

ap = argparse.ArgumentParser()
ap.add_argument('des', nargs='+'); ap.add_argument('--max', type=float, default=1.5); ap.add_argument('--step', type=float, default=0.05)
ap.add_argument('--gap', type=float, default=0.05); ap.add_argument('--tries', type=int, default=60); ap.add_argument('--commit', action='store_true')
ap.add_argument('--drc', action='store_true'); ap.add_argument('--drc-tries', type=int, default=6)
ap.add_argument('--body', action='store_true', help='keep estimated bodies apart instead of silkscreen outlines')
a = ap.parse_args()
MOVE = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'move_part.py')]
W, H = cfg.SIZE_MM
edge = cfg.EDGE / cfg.MIL


def clear(b, others):
    return all(min(b[2], o[2]) - max(b[0], o[0]) + a.gap <= 1e-3 or min(b[3], o[3]) - max(b[1], o[1]) + a.gap <= 1e-3 for o in others)


rc = 0
for des in a.des:
    r = eda.run('comp_bbox.js', 300)
    if not r.get('success'):
        raise SystemExit(f"comp_bbox.js failed: {r.get('error')}")
    P = {f['d']: f for f in r['result']}
    if a.body:
        for p in P.values():
            p['box'] = bodies.body_box(p)[0]
    f = P[des]
    others = [o['box'] for d, o in P.items() if d != des and o['layer'] == f['layer']]
    if clear(f['box'], others):
        print(des, 'already clear'); continue
    n = int(a.max / a.step)
    cands = sorted(((i * a.step, j * a.step) for i in range(-n, n + 1) for j in range(-n, n + 1)), key=lambda d: math.hypot(*d))
    done, tried = None, 0
    if a.drc:
        for dx, dy in cands:
            b = [f['box'][0] + dx, f['box'][1] + dy, f['box'][2] + dx, f['box'][3] + dy]
            if b[0] < edge or b[1] < edge or b[2] > W - edge or b[3] > H - edge or not clear(b, others):
                continue
            tried += 1
            subprocess.run(MOVE + [des, f'{dx:.3f},{dy:.3f}', '--commit', '--force'], capture_output=True, text=True)
            eda.refresh(rebuild=True)
            d = eda.run('drc.js', 900).get('result') or {}
            if d.get('sum') == {}:
                done = (dx, dy); break
            print(' ', des, [round(dx, 3), round(dy, 3)], 'DRC', d.get('sum'), '-> moved back')
            subprocess.run(MOVE + [des, f'{-dx:.3f},{-dy:.3f}', '--commit', '--force'], capture_output=True, text=True)
            eda.refresh()
            if tried >= a.drc_tries:
                break
        print(des, f'moved {[round(v, 3) for v in done]} mm, DRC clean' if done else f'no DRC-clean move in {tried} tries')
        rc |= not done
        continue
    for dx, dy in cands:
        b = [f['box'][0] + dx, f['box'][1] + dy, f['box'][2] + dx, f['box'][3] + dy]
        if b[0] < edge or b[1] < edge or b[2] > W - edge or b[3] > H - edge or not clear(b, others):
            continue
        tried += 1
        out = subprocess.run(MOVE + [des, f'{dx:.3f},{dy:.3f}'], capture_output=True, text=True).stdout
        if 'conflicts 0' in out:
            done = (dx, dy); break
        if tried >= a.tries:
            break
    if not done:
        print(des, f'no clean move within {a.max} mm ({tried} footprint-clear candidates failed the copper check)'); rc = 1; continue
    print(des, 'move', [round(done[0], 3), round(done[1], 3)], 'mm')
    if a.commit:
        out = subprocess.run(MOVE + [des, f'{done[0]:.3f},{done[1]:.3f}', '--commit'], capture_output=True, text=True).stdout
        print(' ', out.strip().splitlines()[-1][:160])
        eda.refresh()
sys.exit(rc)
