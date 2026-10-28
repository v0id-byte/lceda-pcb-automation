// Dump components+pads, tracks, vias and pour outlines of the active PCB (unit: mil).
await pcb();
const C = eda.pcb_PrimitiveComponent; const out = { comps: [], tracks: [], arcs: [], vias: [], pours: [] };
for (const id of await C.getAllPrimitiveId()) {
  const c = await C.get(id); const pins = await C.getAllPinsByPrimitiveId(id);
  out.comps.push({ id, d: c.designator, l: c.layer, x: c.x, y: c.y, r: c.rotation, locked: c.primitiveLock,
    pads: (pins || []).map(p => ({ n: p.padNumber, net: p.net, x: p.x, y: p.y, l: p.layer, rot: p.rotation, pad: p.pad, hole: p.hole })) });
}
const L = eda.pcb_PrimitiveLine;
for (const id of await L.getAllPrimitiveId()) { const t = await L.get(id);
  out.tracks.push({ id, net: t.net, l: t.layer, x1: t.startX, y1: t.startY, x2: t.endX, y2: t.endY, w: t.lineWidth, lk: t.primitiveLock }); }
const A = eda.pcb_PrimitiveArc;
for (const id of await A.getAllPrimitiveId()) { const t = await A.get(id);
  out.arcs.push({ id, net: t.net, l: t.layer, x1: t.startX, y1: t.startY, x2: t.endX, y2: t.endY, ang: t.arcAngle, w: t.lineWidth }); }
const V = eda.pcb_PrimitiveVia;
for (const id of await V.getAllPrimitiveId()) { const v = await V.get(id);
  out.vias.push({ id, net: v.net, x: v.x, y: v.y, hole: v.holeDiameter, dia: v.diameter }); }
const P = eda.pcb_PrimitivePour;
for (const id of await P.getAllPrimitiveId()) { const p = await P.get(id);
  out.pours.push({ id, net: p.net, l: p.layer, name: p.pourName, poly: p.complexPolygon && p.complexPolygon.polygon }); }
return out;
