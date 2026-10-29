// Add a solid pour over the whole board outline (inset by margin) on each listed layer, then pour it.
// ARGS = {net: "GND", layers: [1, 2], margin_mm: 0.3, priority: 1}
// Priority 1 is the highest: a new pour with a larger number fills nothing under an existing one.
await pcb();
const MIL = 39.37, [OX, OY] = CFG.board.origin_mil, [W, H] = CFG.board.size_mm;
const m = (ARGS.margin_mm ?? 0.3) * MIL, x0 = OX + m, x1 = OX + W * MIL - m, y0 = OY - m, y1 = OY - H * MIL + m;
const poly = eda.pcb_MathPolygon.createPolygon([x0, y0, 'L', x1, y0, x1, y1, x0, y1, x0, y0]);
const out = [];
for (const L of ARGS.layers || [1, 2]) {
  const p = await eda.pcb_PrimitivePour.create(ARGS.net || CFG.gnd_net || 'GND', L, poly, 'solid', false, `${ARGS.net || 'GND'}_L${L}`, ARGS.priority ?? 1, 0.2, false);
  await p.rebuildCopperRegion();
  out.push(p.getState_PrimitiveId());
}
return out;
