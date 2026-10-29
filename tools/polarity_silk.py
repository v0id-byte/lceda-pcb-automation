"""polarity_silk.py CAM_DIR [--text 'Board RevA'] [--text-side 2] [--text-at x,y] [--dam 0.15] : polarity-only silkscreen.

For a board ordered without its full silkscreen (cam_export.py --no-silk), the fab still needs to see
polarity. This writes a GTO and a GBO holding only pin-1 dots, '+' beside electrolytic caps and a bar
at each cathode (rules in lib/polarity.py), plus an optional line of text, into CAM_DIR/gerber and the
Gerber zip. The project's own silkscreen is not used. Each mark sits just outside its pad, clear of
every solder-mask opening by --dam mm, and outside other parts' bodies where there is room.
--text-at is board mm (text centre); without it a free spot is searched. Run camcheck.py afterwards.
"""
import argparse, glob, math, os, zipfile
import _boot  # noqa: F401
import bodies, camgeo, cfg, eda, pcbgeo, polarity
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

ap = argparse.ArgumentParser(); ap.add_argument('cam')
ap.add_argument('--text', default=''); ap.add_argument('--text-side', type=int, default=2)
ap.add_argument('--text-at'); ap.add_argument('--text-h', type=float, default=1.2, help='cap height, mm')
ap.add_argument('--dam', type=float, default=0.15, help='min distance from silk to a mask opening, mm')
a = ap.parse_args()
GD = os.path.join(a.cam, 'gerber')
OX, OY = cfg.OX / cfg.MIL, cfg.OY / cfg.MIL   # board mm -> Gerber mm: (x + OX, OY - y)


def g_box(b):
    return box(b[0] + OX, OY - b[3], b[2] + OX, OY - b[1])


r = eda.run('comp_bbox.js', 300)
if not r.get('success'):
    raise SystemExit(f"comp_bbox.js failed: {r.get('error')}")
parts = {f['d']: f for f in r['result']}
g, objs = pcbgeo.load()
pads = [o for o in objs if o['kind'] == 'pad' and o.get('ref') not in (None, '__SLOT')]
R = polarity.Rules(list(parts.values()), pads)
S = 1 / cfg.MIL   # raw LCEDA mil -> Gerber mm
board = affinity.scale(pcbgeo.OUTLINE, S, S, origin=(0, 0)).buffer(-0.25)
mask = {1: camgeo.load(os.path.join(GD, 'Gerber_TopSolderMaskLayer.GTS'))[0].buffer(a.dam),
        2: camgeo.load(os.path.join(GD, 'Gerber_BottomSolderMaskLayer.GBS'))[0].buffer(a.dam)}
body = {d: g_box(bodies.body_box(f)[0]) for d, f in parts.items()}
placed = {1: [], 2: []}


def free(shape, side, own, strict, marks=True):
    if not board.contains(shape) or shape.intersects(mask[side]):
        return False
    if marks and any(shape.distance(m) < 0.15 for m in placed[side]):
        return False
    return not strict or not any(shape.intersects(body[d]) for d, f in parts.items()
                                 if f['layer'] == side and (d != own or strict == 2))


def mark_shape(kind, c, u, across):
    """kind at centre c; u: unit vector pointing away from the part; across: bar length, mm."""
    if kind == 'pin1':
        return Point(*c).buffer(0.25, 16)
    if kind == '+':
        return unary_union([box(c[0] - 0.5, c[1] - 0.08, c[0] + 0.5, c[1] + 0.08),
                            box(c[0] - 0.08, c[1] - 0.5, c[0] + 0.08, c[1] + 0.5)])
    bar = box(-0.13, -across / 2, 0.13, across / 2)   # 'K': a bar across the part axis
    return affinity.translate(affinity.rotate(bar, math.atan2(u[1], u[0]), origin=(0, 0), use_radians=True), *c)


missing, jobs = [], []
for p in pads:
    n = p['id'].split('.')[-1]; ref = p['ref']; kind = R.mark(ref, n)
    if not kind:
        continue
    f = parts[ref]; side = f['layer']
    ps = affinity.scale(p['shape'], S, S, origin=(0, 0)); pc = (p['x'] * S, p['y'] * S)
    own = [q for q in pads if q['ref'] == ref]   # pad centroid: the footprint origin can be off-centre
    cc = (sum(q['x'] for q in own) * S / len(own), sum(q['y'] for q in own) * S / len(own))
    ux, uy = pc[0] - cc[0], pc[1] - cc[1]; L = math.hypot(ux, uy)
    out = (ux / L, uy / L) if L > 1e-6 else (0.0, 1.0)
    ext = max((x - pc[0]) * out[0] + (y - pc[1]) * out[1] for x, y in ps.exterior.coords) if ps.geom_type == 'Polygon' else 0.5
    bb = body[ref].bounds
    across = max(0.8, abs(out[0]) * (bb[3] - bb[1]) + abs(out[1]) * (bb[2] - bb[0]))
    own_s = [(q['id'], affinity.scale(q['shape'], S, S, origin=(0, 0))) for q in own]

    def clear_of_others(m):   # the mark must sit closest to its own pin, or it points at the wrong one
        d0 = m.distance(ps)
        return all(m.distance(q) > d0 + 0.2 for i, q in own_s if i != p['id'])

    if kind == 'K':   # a bar beyond the cathode end, across the part axis
        cands = [(pc[0] + out[0] * (ext + gap + 0.13), pc[1] + out[1] * (ext + gap + 0.13)) for gap in (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)]
    else:             # anywhere around the pad, nearest first; a '+' may have to go out past a big can
        rmax, st = (ext + 7.0, 0.1) if kind == '+' else (ext + 1.6, 0.05)   # measured from the pad edge
        k = int(rmax / st)
        cands = sorted(((pc[0] + i * st, pc[1] + j * st) for i in range(-k, k + 1) for j in range(-k, k + 1)
                        if i * i + j * j <= k * k), key=lambda c: math.hypot(c[0] - pc[0], c[1] - pc[1]))
    opts = []   # (strictness, mark) best first, other marks ignored for now
    for strict in (2, 1, 0):   # outside every body, then allow its own, then any body
        n_ok = 0
        for c in cands:
            m = mark_shape(kind, c, out, across)
            if clear_of_others(m) and free(m, side, ref, strict, marks=False):   # mask covers its own pad too
                opts.append((strict, m)); n_ok += 1
                if n_ok >= 200:
                    break
    jobs.append((p['id'], kind, side, opts))



def tightness(job):   # most constrained first, so a mark with one good spot does not lose it to one with many
    opts = job[3]
    return (-opts[0][0], sum(o[0] == opts[0][0] for o in opts)) if opts else (1, 0)


for pid, kind, side, opts in sorted(jobs, key=tightness):
    m = next((m for _, m in opts if all(m.distance(q) >= 0.15 for q in placed[side])), None)
    if m is None:
        missing.append(f'{pid} {kind}')
    else:
        placed[side].append(m)
        if next(o[0] for o in opts if o[1] is m) < 2:
            print(f'{pid} {kind}: under a part body (no free spot outside)')

if a.text:
    tp = TextPath((0, 0), a.text, size=1, prop=FontProperties(family='DejaVu Sans', weight='bold'))
    polys = []
    for ring in tp.to_polygons():
        if len(ring) >= 3:
            polys.append(Polygon(ring).buffer(0))
    txt = polys[0]
    for q in polys[1:]:
        txt = txt.symmetric_difference(q)   # even-odd: counters become holes
    k = a.text_h / (TextPath((0, 0), 'H', size=1).get_extents().height)
    txt = affinity.scale(txt, k, k, origin=(0, 0))
    if a.text_side == 2:
        txt = affinity.scale(txt, -1, 1, origin=(0, 0))   # reads correctly from the bottom
    b = txt.bounds; txt = affinity.translate(txt, -(b[0] + b[2]) / 2, -(b[1] + b[3]) / 2)
    if a.text_at:
        x, y = map(float, a.text_at.split(','))
        spots = [(x + OX, OY - y)]
    else:
        bb = board.bounds
        spots = [(bb[0] + i * 0.25, bb[1] + j * 0.25) for j in range(int((bb[3] - bb[1]) / 0.25))
                 for i in range(int((bb[2] - bb[0]) / 0.25))]
    for c in spots:
        s = affinity.translate(txt, *c)
        if free(s.envelope.buffer(0.1), a.text_side, None, 2):
            placed[a.text_side].append(s)
            print('text at board mm', (round(c[0] - OX, 2), round(OY - c[1], 2)))
            break
    else:
        missing.append('text')


def gerber(geom, layer):
    fmt = lambda v: str(int(round(v * 1e5)))
    out = [f'G04 Layer: {layer}*', 'G04 Polarity-only silkscreen, tools/polarity_silk.py*',
           '%FSLAX45Y45*%', '%MOMM*%', 'G01*']
    parts_ = sorted(getattr(geom, 'geoms', [geom]), key=lambda q: -q.area)   # big first: holes clear only themselves
    for q in parts_:
        if q.is_empty:
            continue
        for k, ring in enumerate([q.exterior] + list(q.interiors)):
            out.append('%LPD*%' if k == 0 else '%LPC*%')
            pts = list(ring.coords)
            out += ['G36*', f'X{fmt(pts[0][0])}Y{fmt(pts[0][1])}D02*']
            out += [f'X{fmt(x)}Y{fmt(y)}D01*' for x, y in pts[1:]]
            out.append('G37*')
    out.append('%LPD*%'); out.append('M02*')
    return '\n'.join(out) + '\n'


files = {}
for side, name in ((1, 'Gerber_TopSilkscreenLayer.GTO'), (2, 'Gerber_BottomSilkscreenLayer.GBO')):
    geom = unary_union(placed[side]).difference(mask[side]) if placed[side] else Polygon()
    files[name] = gerber(geom, name.split('_')[1].split('.')[0])
    open(os.path.join(GD, name), 'w').write(files[name])
    print(name, len(placed[side]), 'marks')
for z in glob.glob(os.path.join(a.cam, '*_gerber.zip')):
    with zipfile.ZipFile(z) as Z:
        keep = [(i, Z.read(i)) for i in Z.infolist() if not i.filename.upper().endswith(('.GTO', '.GBO'))]
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as Z:
        for i, data in keep:
            Z.writestr(i, data)
        for name, text in files.items():
            Z.writestr(name, text)
    print('added to', os.path.basename(z))
print('not placed:', missing or 'none')
