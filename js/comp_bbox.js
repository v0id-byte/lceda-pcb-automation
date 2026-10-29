// Footprint extents of every component (pads + footprint silkscreen, designator text excluded),
// in board mm (y down). Used by tools/courtyard.py. Returns [{d, layer, tht, fp, x, y, rot, box: [x0, y0, x1, y1]}].
await pcb();
const MIL = 39.37, [OX, OY] = CFG.board.origin_mil, out = [];
for (const c of await eda.pcb_PrimitiveComponent.getAll()) {
  const b = await eda.pcb_Primitive.getPrimitivesBBox([c.getState_PrimitiveId()]);
  if (!b) continue;
  const pins = await eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(c.getState_PrimitiveId());
  const f = c.getState_Footprint() || {};
  out.push({ d: c.getState_Designator(), layer: c.getState_Layer(), tht: pins.some(p => p.getState_Layer() === 12),
    fp: f.name || '', x: +((c.getState_X() - OX) / MIL).toFixed(3), y: +((OY - c.getState_Y()) / MIL).toFixed(3), rot: c.getState_Rotation(),
    box: [(b.minX - OX) / MIL, (OY - b.maxY) / MIL, (b.maxX - OX) / MIL, (OY - b.minY) / MIL].map(v => +v.toFixed(3)) });
}
return out;
