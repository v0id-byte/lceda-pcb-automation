// Schematic netlist (.enet JSON text). components[uid].pinInfoMap[pin].net = resolved net.
await eda.dmt_EditorControl.openDocument(CFG.sch_pages[0]); try { await eda.dmt_EditorControl.waitForDocumentReady(); } catch (e) {}
const f = await eda.sch_ManufactureData.getNetlistFile(); const text = await f.text();
await pcb();
return { text };
