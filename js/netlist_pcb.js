// PCB netlist (.enet JSON text), same format as netlist_sch.js.
await pcb();
const f = await eda.pcb_ManufactureData.getNetlistFile(); return { text: await f.text() };
