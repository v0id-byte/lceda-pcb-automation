// Push schematic changes into the PCB (Design > Update PCB). Run it TWICE: the first pass can leave
// nets half-applied. Then diff netlist_sch vs netlist_pcb.
await pcb();
let r; try { r = await eda.pcb_Document.importChanges(CFG.pcb_doc, true); } catch (e) { r = 'ERR ' + e; }
return r;
