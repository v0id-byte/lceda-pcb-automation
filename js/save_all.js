// Save every schematic page and the PCB listed in CFG. Verify the .eprj2 mtime afterwards:
// save() can return true without persisting. Run it twice before trusting the file on disk.
const o = {};
for (const pg of (CFG.sch_pages || [])) {
  try { await eda.dmt_EditorControl.openDocument(pg); try { await eda.dmt_EditorControl.waitForDocumentReady(); } catch (e) {}
        o[pg] = await eda.sch_Document.save(); } catch (e) { o[pg] = 'ERR ' + e; }
}
await pcb(); o.pcb = await eda.pcb_Document.save(CFG.pcb_doc);
return o;
