"""Estimated component body boxes, for boards that ship without silkscreen (where only bodies and pads
must stay apart). The body size comes from the footprint name: standard chip sizes (0402, 0603, ...)
or an explicit L<len>-W<width> in mm, as LCEDA's library names most footprints. Anything else falls back
to the footprint outline from comp_bbox.js, which is conservative."""
import math
import re

CHIP = {'0201': (0.6, 0.3), '0402': (1.0, 0.5), '0603': (1.6, 0.8), '0805': (2.0, 1.25), '1206': (3.2, 1.6),
        '1210': (3.2, 2.5), '1812': (4.5, 3.2), '2010': (5.0, 2.5), '2512': (6.4, 3.2), '2920': (7.4, 5.1)}


def size(fp):
    m = re.match(r'^[A-Z]*?(0201|0402|0603|0805|1206|1210|1812|2010|2512|2920)\b', fp or '')
    if m:
        return CHIP[m.group(1)]
    m = re.search(r'L(\d+(?:\.\d+)?)-W(\d+(?:\.\d+)?)', fp or '')
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def body_box(f):
    """f: one entry from comp_bbox.js. Returns ([x0, y0, x1, y1] mm, estimated: bool)."""
    s = size(f.get('fp'))
    if not s or 'x' not in f:
        return f['box'], False
    L, W = s
    t = math.radians(f.get('rot') or 0)
    hx = abs(L * math.cos(t)) / 2 + abs(W * math.sin(t)) / 2
    hy = abs(L * math.sin(t)) / 2 + abs(W * math.cos(t)) / 2
    return [f['x'] - hx, f['y'] - hy, f['x'] + hx, f['y'] + hy], True
