"""Project configuration and unit helpers.

All geometry is handled in LCEDA's native unit, the mil (1 mm = 39.37 mil).
Board coordinates in millimetres are (x to the right, y downwards) measured from
the board's top-left corner, which sits at `board.origin_mil` in LCEDA space
(LCEDA's Y axis points up, so y_mm = (origin_y - Y) / 39.37).

The working directory (holding project.json, sid.txt and the exported geometry)
comes from $LCEDA_WORK, falling back to the current directory.
"""
import json
import os

MIL = 39.37
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.abspath(os.environ.get('LCEDA_WORK', os.getcwd()))


def path(name):
    return os.path.join(WORK, name)


def _load():
    p = path('project.json')
    if not os.path.exists(p):
        raise SystemExit(f'no project.json in {WORK} (set LCEDA_WORK, see examples/project.example.json)')
    return json.load(open(p))


CFG = _load()
OX, OY = CFG['board']['origin_mil']
SIZE_MM = CFG['board']['size_mm']
CU = CFG['layers']['copper']                        # e.g. [1, 15, 16, 2]  (1 = top, 2 = bottom, 15.. = inner)
PLANES = CFG['layers'].get('planes', [])            # inner layers flooded with the ground pour
ROUTE_LAYERS = tuple(CFG['layers'].get('route', CU))
GND = CFG.get('gnd_net', 'GND')
CLR = CFG['clearance']['default_mil']               # base copper clearance
CLR_STRONG = CFG['clearance'].get('strong_mil', CLR)
STRONG = set(CFG['clearance'].get('strong_nets', []))  # nets whose rule class asks for CLR_STRONG
EDGE = CFG['clearance'].get('edge_mil', 12)
VIA = tuple(CFG.get('via', {}).get('default_mil', [12, 24]))  # (hole, diameter)


def X(x_mm):
    return OX + x_mm * MIL


def Y(y_mm):
    return OY - y_mm * MIL


def mm(Xmil, Ymil, nd=3):
    return (round((Xmil - OX) / MIL, nd), round((OY - Ymil) / MIL, nd))


def box_mm(x0, y0, x1, y1):
    """mm rectangle (any corner order) -> shapely box in mil"""
    from shapely.geometry import box
    return box(min(X(x0), X(x1)), min(Y(y0), Y(y1)), max(X(x0), X(x1)), max(Y(y0), Y(y1)))
