// Re-pour every copper area (needed after any copper edit, before DRC / export_poured / Gerber).
await pcb();
const r = [];
for (const id of await eda.pcb_PrimitivePour.getAllPrimitiveId()) {
  const p = await eda.pcb_PrimitivePour.get(id); await p.rebuildCopperRegion(); r.push(p.pourName + ':' + p.pourPriority); }
return r.join(' ');
