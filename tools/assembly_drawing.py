"""assembly_drawing.py OUT.pdf [--title TEXT] : assembly / designator drawing, one page per side.

For boards ordered without silkscreen (or with silkscreen too dense to read): board outline, every
footprint outline (pads + footprint silkscreen extent, from js/comp_bbox.js), pads, pin 1 in red, and
the designator in the middle of each part. The bottom page is mirrored, as seen from the bottom.
Needs a fresh geom.json (tools/refresh.py).
"""
import argparse, json
import _boot  # noqa: F401
import cfg, eda, pcbgeo
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle, Polygon as MPoly

ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('--title', default='')
a = ap.parse_args()
r = eda.run('comp_bbox.js', 300)
if not r.get('success'):
    raise SystemExit(f"comp_bbox.js failed: {r.get('error')}")
parts = r['result']
g, objs = pcbgeo.load()
pads = [o for o in objs if o['kind'] == 'pad' and o.get('ref') not in (None, '__SLOT')]
W, H = cfg.SIZE_MM


def mm_xy(x, y):
    return (x - cfg.OX) / cfg.MIL, (cfg.OY - y) / cfg.MIL


PT = 16.5 * 72 / W   # points per mm on the page
POLAR = ('U', 'Q', 'D', 'LED', 'J', 'CN', 'SW')
NPADS = {}
for p in pads:
    NPADS[p['ref']] = NPADS.get(p['ref'], 0) + 1

with PdfPages(a.out) as pdf:
    for side, name in ((1, 'TOP'), (2, 'BOTTOM (mirrored, seen from below)')):
        fig, ax = plt.subplots(figsize=(16.5, 16.5 * H / W + 1.2))
        sx = (lambda x: W - x) if side == 2 else (lambda x: x)
        ax.add_patch(Rectangle((0, 0), W, H, fill=False, lw=1.2, ec='black'))
        for o in pcbgeo.KEEPOUT.geoms if hasattr(pcbgeo.KEEPOUT, 'geoms') else [pcbgeo.KEEPOUT]:
            if not o.is_empty:
                ax.add_patch(MPoly([(sx(x), y) for x, y in (mm_xy(*c) for c in o.exterior.coords)], fill=False, ls=':', ec='grey', lw=0.6))
        for p in pads:
            if side not in p['layers']:
                continue
            ring = p['shape'].exterior.coords if p['shape'].geom_type == 'Polygon' else p['shape'].convex_hull.exterior.coords
            is1 = p['id'].split('.')[-1] in ('1', 'A1') and (NPADS.get(p['ref'], 0) > 2 or p['ref'].startswith(POLAR))
            ax.add_patch(MPoly([(sx(x), y) for x, y in (mm_xy(*c) for c in ring)], fc='#d33' if is1 else '#bbb', ec='none', alpha=0.8))
        for f in parts:
            if f['layer'] != side:
                continue
            x0, y0, x1, y1 = f['box']
            ax.add_patch(Rectangle((min(sx(x0), sx(x1)), y0), abs(x1 - x0), y1 - y0, fill=False, lw=0.7, ec='#1a4fbf'))
            cx, cy = sx((x0 + x1) / 2), (y0 + y1) / 2
            bw, bh = abs(x1 - x0), y1 - y0
            tall = bh > bw * 1.2
            fs = max(4.0, min(11.0, max(bw, bh) * PT / (0.62 * max(2, len(f['d']))), min(bw, bh) * PT * 0.9))
            ax.text(cx, cy, f['d'], ha='center', va='center', fontsize=fs, color='black', weight='bold', rotation=90 if tall else 0)
        ax.set_xlim(-1, W + 1); ax.set_ylim(H + 1, -1); ax.set_aspect('equal'); ax.axis('off')
        ax.set_title(f"{a.title}  {name}  ({sum(1 for f in parts if f['layer'] == side)} parts; red = pin 1 of ICs / polarised parts)", fontsize=11)
        pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)
print('wrote', a.out)
