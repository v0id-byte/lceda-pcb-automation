"""Grid A* router on real LCEDA geometry (unit: mil, grid R mil).

route() connects any copper of `src_objs` to any copper of `dst_objs` for one net, on the given
layers, honouring other-net copper + clearance, board edge, keepouts and via rules. It returns a list
of ('T', layer, x1, y1, x2, y2) and ('V', x, y) items; nothing is written to the board. Check the
items with check.conflicts() and commit them with eda.commit_items().

The ground pour is never an obstacle (pours are re-carved around new copper on rebuild), so plan
signal routes on plane layers sparingly: every track on a plane layer cuts the plane.
"""
import sys, math, heapq, json
import numpy as np, shapely
from shapely.geometry import box, Point, LineString
from shapely.ops import unary_union
import pcbgeo, cfg
def pclr(clr, other, net=None):
    """clearance to keep from copper of net `other`: nets in the strong class get the larger rule.
    `clr` may carry a margin (+0.3 when routing, -0.02 when checking)."""
    extra = cfg.CLR_STRONG - cfg.CLR
    return clr + extra if (other in cfg.STRONG and clr < cfg.CLR_STRONG - 0.1) else clr

R = 2.5  # grid resolution

class Board:
    def __init__(self, geom=None, poured=None):
        self.g, self.objs = pcbgeo.load(geom, poured)
        self.added = []  # objs we created this session (same format)

    def all_objs(self):
        return self.objs + self.added

    def islands(self, net):
        return pcbgeo.islands(self.all_objs(), net)

    def add_track(self, net, L, x1, y1, x2, y2, w):
        s = LineString([(x1, y1), (x2, y2)]).buffer(w / 2, 8)
        self.added.append(dict(kind='track', id='new', net=net, layers=[L], shape=s, w=w, x1=x1, y1=y1, x2=x2, y2=y2))

    def add_via(self, net, x, y, hole, dia):
        self.added.append(dict(kind='via', id='new', net=net, layers=list(pcbgeo.CU), shape=Point(x, y).buffer(dia / 2, 12), x=x, y=y, dia=dia, hole=hole))

    def remove(self, pred):
        self.objs = [o for o in self.objs if not pred(o)]
        self.added = [o for o in self.added if not pred(o)]


def raster(shapes, X, Y):
    """boolean grid: point inside any shape"""
    m = np.zeros(X.shape, bool)
    if not shapes:
        return m
    x0, y0 = X[0, 0], Y[0, 0]
    for s in shapes:
        b = s.bounds
        i0 = max(0, int((b[0] - x0) / R) - 1); i1 = min(X.shape[1], int((b[2] - x0) / R) + 2)
        j0 = max(0, int((b[1] - y0) / R) - 1); j1 = min(X.shape[0], int((b[3] - y0) / R) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        sub = shapely.contains_xy(s, X[j0:j1, i0:i1], Y[j0:j1, i0:i1])
        m[j0:j1, i0:i1] |= sub
    return m


def route(board, net, src_objs, dst_objs, w, clr, window, layers=None, layer_cost=None,
          via=(12, 24), via_clr=None, via_cost=60, edge=12, avoid_pour_nets=True, hole_clr=12, maxexp=4_000_000, reserve=(), via_thru_pour=(), clr_track=None):
    """route from any src copper to any dst copper. returns list of ('T',L,x1,y1,x2,y2) and ('V',x,y)"""
    layers = tuple(layers or cfg.ROUTE_LAYERS)
    layer_cost = layer_cost or {L: (2.5 if L in cfg.PLANES else 1.0) for L in layers}
    via_clr = clr if via_clr is None else via_clr
    x0, y0, x1, y1 = window
    xs = np.arange(x0, x1, R); ys = np.arange(y0, y1, R)
    X, Y = np.meshgrid(xs, ys)
    win = box(x0 - 60, y0 - 60, x1 + 60, y1 + 60)
    allo = [o for o in board.all_objs() if o['shape'].intersects(win)]
    free_area = pcbgeo.OUTLINE.buffer(-(edge + w / 2)).difference(pcbgeo.KEEPOUT.buffer(clr + w / 2))
    free_via = pcbgeo.OUTLINE.buffer(-(edge + via[1] / 2)).difference(pcbgeo.KEEPOUT.buffer(via_clr + via[1] / 2))
    inb = raster([free_area], X, Y); inb_v = raster([free_via], X, Y)
    LI = {L: i for i, L in enumerate(layers)}
    blocked = {}; viablock = np.zeros(X.shape, bool)
    holes = []
    for L in pcbgeo.CU:
        other = [o for o in allo if L in o['layers'] and o['net'] != net and not (o['kind'] == 'pour' and o['net'] == cfg.GND)]
        ob = [o['shape'].buffer((clr_track if (clr_track and o['kind']=='track') else pclr(clr, o['net'])) + w / 2, 6) for o in other]
        rs = [r['shape'].buffer(clr + w / 2 + r.get('extra', 10), 6) for r in reserve if r['net'] != net and L in r['layers'] and r['shape'].intersects(win)]
        blocked[L] = raster(ob + rs, X, Y) | ~inb
        # plane layers listed in via_thru_pour: the pour re-carves its own clearance around a new via
        vo = [o for o in other if not (L in via_thru_pour and o['kind'] == 'pour')]
        viablock |= raster([o['shape'].buffer(pclr(via_clr, o['net']) + via[1] / 2, 6) for o in vo], X, Y)
    # own smd pads: no via-in-pad
    own_smd = [o['shape'].buffer(via[1] / 2 + 2) for o in allo if o['net'] == net and o['kind'] == 'pad' and len(o['layers']) == 1]
    viablock |= raster(own_smd, X, Y)
    # hole to hole
    hs = [Point(o['x'], o['y']).buffer(o.get('hole', 12) / 2 + hole_clr + via[0] / 2) for o in allo if o['kind'] == 'via']
    viablock |= raster(hs, X, Y)
    viablock |= ~inb_v
    def cells(objs):
        out = set()
        for o in objs:
            for L in o['layers']:
                if L not in LI:
                    continue
                m = raster([o['shape'].buffer(-0.5) if o['shape'].area > 4 else o['shape']], X, Y)
                for j, i in zip(*np.nonzero(m)):
                    out.add((LI[L], j, i))
        return out
    S = cells(src_objs); T = cells(dst_objs)
    if not S or not T:
        return None, 'no src/dst cells'
    # own copper is passable
    for (li, j, i) in S | T:
        pass
    passable = {}
    for L in layers:
        owns = [o['shape'].buffer(-w / 2 + 0.5) for o in allo if o['net'] == net and L in o['layers'] and o['kind'] != 'pour']
        owns = [s for s in owns if not s.is_empty]
        own = raster(owns, X, Y)
        passable[LI[L]] = (~blocked[L]) | own
    S = {c for c in S if passable[c[0]][c[1], c[2]]}; T = {c for c in T if passable[c[0]][c[1], c[2]]}
    if not S or not T:
        return None, 'src/dst not passable at this width'
    tpts = np.array([(xs[i], ys[j]) for (_, j, i) in list(T)[::max(1, len(T) // 200)]])
    def h(j, i):
        d = np.min(np.hypot(tpts[:, 0] - xs[i], tpts[:, 1] - ys[j]))
        return d / R
    nb = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
    lc = [layer_cost[L] for L in layers]
    g = {}; prev = {}; pq = []
    for s in S:
        g[s] = 0; heapq.heappush(pq, (h(s[1], s[2]), 0, s))
    found = None; n = 0
    H, W = X.shape
    while pq:
        f, gc, s = heapq.heappop(pq)
        if gc > g.get(s, 1e18):
            continue
        if s in T:
            found = s; break
        n += 1
        if n > maxexp:
            return None, 'expansion limit'
        li, j, i = s
        pd = prev.get(s)
        for dj, di, c in nb:
            jj, ii = j + dj, i + di
            if not (0 <= jj < H and 0 <= ii < W):
                continue
            if not passable[li][jj, ii]:
                continue
            if dj and di and not (passable[li][j, ii] and passable[li][jj, i]):
                continue
            turn = 0
            if pd is not None and pd[0] == li:
                if (j - pd[1], i - pd[2]) != (dj, di):
                    turn = 0.3
            ns = (li, jj, ii); ng = gc + c * lc[li] + turn
            if ng < g.get(ns, 1e18):
                g[ns] = ng; prev[ns] = s; heapq.heappush(pq, (ng + h(jj, ii), ng, ns))
        if not viablock[j, i]:
            for lj in range(len(layers)):
                if lj == li or not passable[lj][j, i]:
                    continue
                ns = (lj, j, i); ng = gc + via_cost
                if ng < g.get(ns, 1e18):
                    g[ns] = ng; prev[ns] = s; heapq.heappush(pq, (ng + h(j, i), ng, ns))
    if not found:
        route.last=(g,xs,ys,layers,passable,viablock)
        return None, f'no path ({n} exp)'
    path = [found]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    # to geometry
    out = []; seg = [path[0]]
    def flush(seg):
        if len(seg) < 2:
            return
        pts = [(xs[c[2]], ys[c[1]]) for c in seg]
        # merge collinear
        simp = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, b, c2 = simp[-1], pts[k], pts[k + 1]
            d1 = (np.sign(round(b[0] - a[0], 3)), np.sign(round(b[1] - a[1], 3)))
            d2 = (np.sign(round(c2[0] - b[0], 3)), np.sign(round(c2[1] - b[1], 3)))
            if d1 != d2:
                simp.append(b)
        simp.append(pts[-1])
        L = layers[seg[0][0]]
        for a, b in zip(simp, simp[1:]):
            out.append(('T', L, float(a[0]), float(a[1]), float(b[0]), float(b[1])))
    for c in path[1:]:
        if c[0] != seg[-1][0]:
            flush(seg)
            out.append(('V', float(xs[c[2]]), float(ys[c[1]])))
            seg = [c]
        else:
            seg.append(c)
    flush(seg)
    return out, f'ok ({n} exp)'


def to_js(net, items, w, via):
    lines = []
    for it in items:
        if it[0] == 'T':
            _, L, a, b, c, d = it
            lines.append(f'r.push((await eda.pcb_PrimitiveLine.create({json.dumps(net)},{L},{a:.3f},{b:.3f},{c:.3f},{d:.3f},{w})).primitiveId);')
        else:
            _, x, y = it
            lines.append(f'r.push((await eda.pcb_PrimitiveVia.create({json.dumps(net)},{x:.3f},{y:.3f},{via[0]},{via[1]})).primitiveId);')
    return lines
