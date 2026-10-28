// Nets with a non-default rule (spacing class, track width class, via class) and the region rules.
await pcb();
const r = await eda.pcb_Drc.getNetRules();
return { nets: r.filter(x => x['Safe Spacing'] !== 'default' || x['Track'] !== 'default' || x['Via Size'] !== 'default')
                 .map(x => [x.name, x['Safe Spacing'], x['Track'], x['Via Size']]),
         regions: (await eda.pcb_Drc.getRegionRules()).map(x => [x.name, x.constraintName, x.Track]) };
