// Dump the computed copper of every pour (what actually gets fabricated). Rebuild pours first.
await pcb();
const out = [];
for (const id of await eda.pcb_PrimitivePoured.getAllPrimitiveId()) {
  const p = await eda.pcb_PrimitivePoured.get(id); const pr = await eda.pcb_PrimitivePour.get(p.pourPrimitiveId);
  const F = p.pourFills || [];
  out.push({ id, pour: p.pourPrimitiveId, net: pr && pr.net, l: pr && pr.layer,
    fills: F.filter(f => f.fill).map(f => f.path && f.path.complexPolygon),
    strokes: F.filter(f => !f.fill).map(f => [f.lineWidth, f.path && f.path.complexPolygon]) });
}
return out;
