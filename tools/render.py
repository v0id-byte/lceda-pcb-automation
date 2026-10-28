"""render.py x0,y0,x1,y1(mm) LAYERS out.png [--islands NET]

Draw copper of the given layers (e.g. 1,15,16,2) in a board window, with pad/net labels and mm ticks.
--islands NET colours that net's pours green (main island) / red (cut-off pockets): the fastest way to
see why a ground pad is floating."""
import argparse
import _boot  # noqa: F401
import cfg, pcbgeo
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import box

ap = argparse.ArgumentParser(); ap.add_argument('win'); ap.add_argument('layers'); ap.add_argument('out'); ap.add_argument('--islands')
a = ap.parse_args()
x0, y0, x1, y1 = map(float, a.win.split(',')); Ls = [int(v) for v in a.layers.split(',')]
g, objs = pcbgeo.load()
W = cfg.box_mm(x0, y0, x1, y1)
MAIN = set()
if a.islands:
    MAIN = {id(o) for o in max(pcbgeo.islands(objs, a.islands), key=len)}
n = len(Ls); cols = 2 if n > 1 else 1; rows = (n + cols - 1) // cols
fig, axs = plt.subplots(rows, cols, figsize=((x1 - x0) * 1.2 * cols, (y1 - y0) * 1.2 * rows + 1), squeeze=False)


def draw(ax, s, fc, al):
    for p in ([s] if s.geom_type == 'Polygon' else list(getattr(s, 'geoms', []))):
        if p.geom_type == 'Polygon':
            xs, ys = p.exterior.xy; ax.fill(xs, ys, fc=fc, ec='k', alpha=al, lw=0.3)


for ax, L in zip(axs.flat, Ls):
    ax.set_aspect('equal'); ax.set_facecolor('#111'); ax.set_title(f'layer {L}')
    for o in objs:
        if L in o['layers'] and o['kind'] == 'pour' and o['shape'].intersects(W):
            col = ('#2a6' if id(o) in MAIN else '#d33') if (a.islands and o['net'] == a.islands) else '#1e3320'
            draw(ax, o['shape'], col, 0.7)
    for o in objs:
        if L in o['layers'] and o['kind'] != 'pour' and o['shape'].intersects(W):
            draw(ax, o['shape'], {'track': '#88f', 'pad': '#cc0', 'via': '#c80'}[o['kind']], 0.8)
            c = o['shape'].centroid
            if W.contains(c) and o['kind'] != 'track':
                ax.text(c.x, c.y, (o['id'] + ' ' if o['kind'] == 'pad' else '') + o['net'][:10], fontsize=6, color='w', ha='center')
    ax.set_xlim(cfg.X(x0), cfg.X(x1)); ax.set_ylim(cfg.Y(y1), cfg.Y(y0))
    xt = np.arange(np.ceil(x0), x1, 1); yt = np.arange(np.ceil(y0), y1, 1)
    ax.set_xticks([cfg.X(v) for v in xt]); ax.set_xticklabels([f'{v:g}' for v in xt], fontsize=6)
    ax.set_yticks([cfg.Y(v) for v in yt]); ax.set_yticklabels([f'{v:g}' for v in yt], fontsize=6); ax.grid(color='#555', lw=0.3)
plt.tight_layout(); plt.savefig(a.out, dpi=60); print(a.out)
