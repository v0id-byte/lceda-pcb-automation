// List the current project's boards, schematic pages and PCB documents -> fill project.json from this.
const p = await eda.dmt_Project.getCurrentProjectInfo();
const boards = (p.data || []).filter(b => b.itemType === 'Board').map(b => ({
  board: b.name,
  sch_pages: ((b.schematic && b.schematic.page) || []).map(pg => ({ uuid: pg.uuid, name: pg.name })),
  pcb: b.pcb ? { uuid: b.pcb.uuid, name: b.pcb.name } : null,
}));
const loose = (p.data || []).filter(d => d.itemType === 'PCB').map(d => ({ uuid: d.uuid, name: d.name }));
return { project_uuid: p.uuid, name: p.friendlyName, boards, pcbs_without_board: loose };
