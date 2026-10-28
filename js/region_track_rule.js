// Create a narrow-track exception that is scoped to a region, instead of relaxing a global rule.
// ARGS = {rule: "LOWCUR_6_30", base: "copperThickness1oz", min_mm: 0.1524, def_mm: 0.254, max_mm: 0.762,
//         regions: [{name: "LOWCUR_ZONE", poly: [x0,y0, x1,y1, ...] (mil, LCEDA frame)}]}
// Justify every such region in the design notes (e.g. pull-up / logic-supply branches only).
await pcb();
const out = {};
const cfg = (await eda.pcb_Drc.getCurrentRuleConfiguration()).config; const tr = cfg['Physics']['Track'];
if (!tr[ARGS.rule]) {
  const t = JSON.parse(JSON.stringify(tr[ARGS.base])); t.editName = ARGS.rule; t.isSetDefault = false;
  t.form.data['1'] = { minValue: ARGS.min_mm, defaultValue: ARGS.def_mm, maxValue: ARGS.max_mm }; tr[ARGS.rule] = t;
  out.ruleCreated = await eda.pcb_Drc.overwriteCurrentRuleConfiguration(cfg);
}
const made = [];
for (const q of ARGS.regions) {
  const r = await eda.pcb_PrimitiveRegion.create(12, eda.pcb_MathPolygon.createPolygon(q.poly), [9], q.name, 2, false);
  made.push([r.primitiveId, q.name]);
}
const rr = await eda.pcb_Drc.getRegionRules();
for (const [id, nm] of made) rr.push({ type: 'region', name: id, constraintName: nm, 'Safe Spacing': null, 'Copper Safe Spacing': null,
  'Plane Safe Spacing': null, 'Other Spacing': null, 'Track': ARGS.rule, 'Differential Pair': null, 'Via Size': null,
  'Plane Zone': null, 'Copper Zone': null, 'Creepage Distance': null, 'Height': null });
out.regions = await eda.pcb_Drc.overwriteRegionRules(rr); out.made = made;
return out;
