"""Clearance pre-check for planned copper (before anything is written to the board)."""
from shapely.geometry import LineString, Point
import cfg
import pcbgeo
import router


def conflicts(B, net, items, clr, w, via=None, rip=(), edge=None, via_thru_pour=()):
    """Return other-net copper closer than the clearance rule to any planned item.

    items: ('T', layer, x1, y1, x2, y2[, width]) and ('V', x, y) in mil.
    Ground pours never conflict (they re-carve on rebuild). Pours on layers listed in
    `via_thru_pour` are ignored for vias for the same reason.
    Each result is (item head, kind, id, net, layers, distance_mil) or (item head, 'EDGE').
    """
    via = via or cfg.via_for(net)
    edge = cfg.EDGE if edge is None else edge
    rip = set(rip)
    objs = [o for o in B.all_objs() if o['id'] not in rip]
    out = []
    for it in items:
        if it[0] == 'T':
            _, L, a, b, c, d = it[:6]
            ww = it[6] if len(it) > 6 else w
            s = LineString([(a, b), (c, d)]).buffer(ww / 2, 8) if (a, b) != (c, d) else Point(a, b).buffer(ww / 2, 8)
            layers = [L]
        else:
            _, x, y = it[:3]
            s = Point(x, y).buffer(via[1] / 2, 12)
            layers = pcbgeo.CU
        for o in objs:
            if o['net'] == net or (o['kind'] == 'pour' and o['net'] == cfg.GND):
                continue
            if it[0] != 'T' and o['kind'] == 'pour' and set(o['layers']) <= set(via_thru_pour):
                continue
            if not set(layers) & set(o['layers']):
                continue
            d = o['shape'].distance(s)
            if d < router.pclr(clr, o['net']) - 0.01:
                out.append((it[:3], o['kind'], o['id'], o['net'], o['layers'], round(d, 2)))
        if not pcbgeo.OUTLINE.buffer(-edge).contains(s) or s.intersects(pcbgeo.KEEPOUT):
            out.append((it[:3], 'EDGE/KEEPOUT'))
    return out
