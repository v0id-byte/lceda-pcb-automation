// Full DRC. Returns {sum: {"<category> | <net/rule>": count}, full: raw}. Empty sum == clean.
await pcb();
const r = await eda.pcb_Drc.check(true, false, true); const sum = {};
for (const a of r) for (const b of a.list) sum[a.name + ' | ' + b.name] = b.list.length;
return { sum, full: r };
