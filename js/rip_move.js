// ARGS = {rip: [track/via ids], mv: {Designator: [x_mm, y_mm, rotation?, layer?]}}  (layer 1 top, 2 bottom)
// Deletes the listed tracks/vias, moves parts, returns the parts' new pad positions in board mm.
// Bottom-side rotation runs counter-clockwise in LCEDA's (Y-up) frame; moving a part to the other side
// mirrors its pads, so re-check pin positions (often a +180 deg fix is needed).
await pcb();
const MIL = 39.37, [OX, OY] = CFG.board.origin_mil, out = { del: 0, moved: {} };
const ids = new Set(ARGS.rip || []);
const tl = (await eda.pcb_PrimitiveLine.getAll()).map(l => l.getState_PrimitiveId()).filter(i => ids.has(i));
if (tl.length) { await eda.pcb_PrimitiveLine.delete(tl); out.del += tl.length; }
const vl = (await eda.pcb_PrimitiveVia.getAll()).map(v => v.getState_PrimitiveId()).filter(i => ids.has(i));
if (vl.length) { await eda.pcb_PrimitiveVia.delete(vl); out.del += vl.length; }
const C = eda.pcb_PrimitiveComponent;
for (const c of await C.getAll()) {
  const d = c.getState_Designator(); const m = (ARGS.mv || {})[d]; if (!m) continue;
  const id = c.getState_PrimitiveId(); const o = { x: OX + m[0] * MIL, y: OY - m[1] * MIL };
  if (m.length > 2) o.rotation = m[2]; if (m.length > 3) o.layer = m[3];
  await C.modify(id, o);
  out.moved[d] = (await C.getAllPinsByPrimitiveId(id)).map(p => [p.getState_PadNumber(),
    +((p.getState_X() - OX) / MIL).toFixed(3), +((OY - p.getState_Y()) / MIL).toFixed(3), p.getState_Layer()]);
}
return out;
