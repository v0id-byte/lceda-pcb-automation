"""edge_rails.py [--width 5] [--gap 2] [--tabs top:34,bottom:52] [--marks top:8,top:71.4,bottom:8] [--commit]

Add assembly edge rails (工艺边) on the board's two long edges, joined by mouse-bite tabs, so the fab can
run the board through SMT as a single unit without panelizing it (and charging for that). All numbers are
board mm. Creates:
  - the board outline grown to include both rails (the old outline rectangle is replaced);
  - one milled slot (a MULTI-layer fill, i.e. a slot region) of --gap mm between the board and each rail,
    broken by an end bridge at each short edge (--end-w) and by a tab at each --tabs x position (--tab-w);
  - a row of mouse-bite holes (--hole, --pitch) across every bridge and tab, on the rail side of the
    board edge, so breaking leaves no bite in the board itself;
  - fiducials (--mark copper, --mark-open mask opening) on top AND bottom copper at --marks, centred
    --mark-edge mm from the rail's outer edge (place them asymmetrically so a rotated panel is caught);
  - a tooling hole (--tooling) near each rail corner;
  - a no-pour keepout over every tab, --edge mm into the board, so no copper reaches a break line.
Holes are round slot regions and fiducials are a copper disc plus a mask-layer disc, all fills: a pad
created through the API (any type, plated or not) makes every later rebuildCopperRegion() throw
"Cannot read properties of undefined (reading 'length')" in LCEDA Pro 4.1.78.
The board itself (project.json board.size_mm) is unchanged; the rest of the toolchain keeps using it.
Pick tab positions away from side-entry connectors and from MLCCs near the edge. Run DRC, then CAM.
"""
import argparse, json
import _boot  # noqa: F401
import cfg, eda

ap = argparse.ArgumentParser()
ap.add_argument('--width', type=float, default=5.0); ap.add_argument('--gap', type=float, default=2.0)
ap.add_argument('--tabs', default='', help='side:x_mm,... centre of each mid tab, e.g. top:34,bottom:52')
ap.add_argument('--tab-w', type=float, default=4.0); ap.add_argument('--end-w', type=float, default=3.0)
ap.add_argument('--hole', type=float, default=0.55)
ap.add_argument('--pitch', type=float, default=0.9, help='hole centre spacing: 0.35 mm of web between 0.55 mm holes (JLC: 0.35-0.4, min 0.3)')
ap.add_argument('--marks', default='top:8,top:71.4,bottom:8', help='side:x_mm,... fiducial positions')
ap.add_argument('--mark', type=float, default=1.0); ap.add_argument('--mark-open', type=float, default=3.0)
ap.add_argument('--mark-edge', type=float, default=3.85, help='fiducial centre to the rail outer edge, mm')
ap.add_argument('--tooling', type=float, default=2.0); ap.add_argument('--tooling-at', type=float, default=3.5,
                help='tooling hole centre from the short edge, mm')
ap.add_argument('--edge', type=float, default=0.35, help='keepout depth into the board at each tab, mm')
ap.add_argument('--corner', type=float, default=1.0, help='outline corner radius, mm')
ap.add_argument('--replace', action='store_true', help='first delete rail objects from an earlier run (fills and keepouts outside the board)')
ap.add_argument('--commit', action='store_true')
a = ap.parse_args()
W, H = cfg.SIZE_MM; M = cfg.MIL
X = lambda x: round(cfg.X(x), 3); Y = lambda y: round(cfg.Y(y), 3)
R = a.width + a.gap   # rail outer edge distance from the board edge
sides = {'top': (-1, 0.0), 'bottom': (1, H)}   # outward direction in board y, board edge y


def spans(side):
    """Slot x-ranges and bridge x-ranges for one side: end bridge, slot, tab, slot, ..., end bridge."""
    cuts = sorted(float(t.split(':')[1]) for t in a.tabs.split(',') if t.startswith(side + ':'))
    edges = [a.end_w] + [v for c in cuts for v in (c - a.tab_w / 2, c + a.tab_w / 2)] + [W - a.end_w]
    return list(zip(edges[0::2], edges[1::2])), [(0, a.end_w)] + [(c - a.tab_w / 2, c + a.tab_w / 2) for c in cuts] + [(W - a.end_w, W)]


js = ['await pcb();', 'const r = {slots: [], holes: [], marks: [], keepouts: []};']
if a.replace:   # everything an earlier run made lies beyond a long edge or straddles it (keepouts)
    # bounds come from the polygon data: getPrimitivesBBox() returns nothing for slot regions, and a
    # region's name is not kept, so keepouts are recognised by their rule set [6, 7, 8]
    js += ["const bnd = (p) => { const a = p.polygon || p; if (a[0] === 'CIRCLE') return [a[2] - a[3], a[2] + a[3]];"
           " if (a[0] === 'R') return [a[2] - a[4], a[2]]; return null; };   // [minY, maxY]",
           f"const beyond = (b) => b && (b[0] > {Y(0) - 0.5} || b[1] < {Y(H) + 0.5});",
           f"const straddle = (b) => b && ((b[0] < {Y(0)} && b[1] > {Y(0)}) || (b[0] < {Y(H)} && b[1] > {Y(H)}));",
           "const del = [];",
           "for (const f of await eda.pcb_PrimitiveFill.getAll()) if ([1, 2, 5, 6, 12].includes(f.getState_Layer()) && beyond(bnd(f.getState_ComplexPolygon()))) del.push(f.getState_PrimitiveId());",
           "if (del.length) await eda.pcb_PrimitiveFill.delete(del); r.deletedFills = del.length;",
           "const ko = (await eda.pcb_PrimitiveRegion.getAll()).filter(g => { const j = JSON.parse(JSON.stringify(g)); return JSON.stringify(j.ruleType) === '[6,7,8]' && straddle(bnd(j.complexPolygon)); }).map(g => g.getState_PrimitiveId());",
           "if (ko.length) await eda.pcb_PrimitiveRegion.delete(ko); r.deletedKeepouts = ko.length;"]
js += [
      "const disc = async (L, x, y, rad) => (await eda.pcb_PrimitiveFill.create(L, eda.pcb_MathPolygon.createPolygon(['CIRCLE', x, y, rad]))).getState_PrimitiveId();",
      'const hole = (x, y, rad) => disc(12, x, y, rad);   // a round slot region = non-plated hole',
      "const ol = (await eda.pcb_PrimitivePolyline.getAll()).filter(p => p.getState_Layer() === 11);",
      "if (ol.length !== 1) throw new Error('expected one outline polyline, found ' + ol.length);",
      f"r.outline = (await eda.pcb_PrimitivePolyline.modify(ol[0].getState_PrimitiveId(), {{polygon: eda.pcb_MathPolygon.createPolygon(['R', {X(0)}, {Y(-R)}, {round(W * M, 3)}, {round((H + 2 * R) * M, 3)}, 0, {round(a.corner * M, 3)}])}})).getState_PrimitiveId();"]
plan = [f'outline -> panel {W:.3f} x {H + 2 * R:.3f} mm']
for side, (out, ye) in sides.items():
    slots, bridges = spans(side)
    y0, y1 = sorted((ye, ye + out * a.gap))
    for x0, x1 in slots:   # slot region with round ends (a router bit cuts them round anyway)
        js.append(f"r.slots.push((await eda.pcb_PrimitiveFill.create(12, eda.pcb_MathPolygon.createPolygon(['R', {X(x0)}, {Y(y0)}, {round((x1 - x0) * M, 3)}, {round(a.gap * M, 3)}, 0, {round(a.gap / 2 * M, 3)}]))).getState_PrimitiveId());")
        plan.append(f'{side} slot x {x0:.2f}-{x1:.2f}, y {y0:.2f}-{y1:.2f}')
    yh = ye + out * a.hole / 2   # bite holes tangent to the board edge, on the rail side
    for b0, b1 in bridges:
        # 0.3 mm from the panel's outer edge; next to a slot its round end leaves ~0.31 mm of extra
        # material at the break line, so a hole centre 0.265 mm inside the bridge is 0.3 mm from the slot
        lo = b0 + (a.hole / 2 + 0.3 if b0 <= 0 else 0.265)
        hi = b1 - (a.hole / 2 + 0.3 if b1 >= W else 0.265)
        n = max(2, int((hi - lo) / a.pitch) + 1)
        xs = [(lo + hi) / 2 + (i - (n - 1) / 2) * a.pitch for i in range(n)]
        for x in xs:
            js.append(f"r.holes.push(await hole({X(x)}, {Y(yh)}, {round(a.hole / 2 * M, 3)}));")
        plan.append(f'{side} bridge x {b0:.2f}-{b1:.2f}: {len(xs)} bite holes at x {", ".join(f"{x:.2f}" for x in xs)}, y {yh:.3f}')
        k0, k1 = sorted((ye - out * a.edge, ye + out * a.gap))   # no pour from inside the board edge across the tab
        ext = a.gap / 2 + 0.3   # past the slot's round end, where the board edge is not cut yet
        js.append(f"r.keepouts.push((await eda.pcb_PrimitiveRegion.create(12, eda.pcb_MathPolygon.createPolygon(['R', {X(b0 - ext)}, {Y(k0)}, {round((b1 - b0 + 2 * ext) * M, 3)}, {round((k1 - k0) * M, 3)}, 0, 0]), [6, 7, 8], 'RAIL_TAB_KEEPOUT')).getState_PrimitiveId());")
    ym = ye + out * (R - a.mark_edge)
    for t in a.marks.split(','):
        s, x = t.split(':')
        if s != side:
            continue
        for L, mask in ((1, 5), (2, 6)):   # copper disc + mask opening, top and bottom
            js.append(f"r.marks.push(await disc({L}, {X(float(x))}, {Y(ym)}, {round(a.mark / 2 * M, 3)}), await disc({mask}, {X(float(x))}, {Y(ym)}, {round(a.mark_open / 2 * M, 3)}));")
        plan.append(f'{side} fiducial at x {float(x):.2f}, y {ym:.2f} (top + bottom copper)')
    yt = ye + out * (a.gap + a.width / 2)
    for x in (a.tooling_at, W - a.tooling_at):
        js.append(f"r.holes.push(await hole({X(x)}, {Y(yt)}, {round(a.tooling / 2 * M, 3)}));")
        plan.append(f'{side} tooling hole at x {x:.2f}, y {yt:.2f}')
js.append('return r;')
print('\n'.join(plan))
if a.commit:
    res = eda.run_code('\n'.join(js), 300)
    print('COMMIT', json.dumps(res)[:600])
else:
    open(cfg.path('edge_rails.js'), 'w').write('\n'.join(js)); print('dry run: JS in', cfg.path('edge_rails.js'))
