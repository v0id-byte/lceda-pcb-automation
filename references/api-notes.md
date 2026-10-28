# LCEDA Pro 4.x API notes (what this toolkit relies on)

Discover anything else live, inside a script:
`Object.getOwnPropertyNames(Object.getPrototypeOf(eda.pcb_Drc))`, `String(eda.pcb_Drc.check).slice(0, 400)`.
Read a method's source before calling it: some methods open modal dialogs and hang the session.
The CLI itself documents the API: `LCEDA-Pro doc api --help`.

## CLI
- `LCEDA-Pro open --path X.eprj2 [--headless true]` → session id. `LCEDA-Pro session list` shows all
  windows. A session the user opened in the GUI can also be driven if you know its id.
- `LCEDA-Pro invoke --session SID --code-file f.js --timeout ms [--args '{...}']`. The code is an async
  function body; `return` gives `value`. The output is `{"ok", "value", "error", "logs", "durationMs"}`.

## Documents
- `eda.dmt_Project.getCurrentProjectInfo()` → boards, schematic pages, PCB uuids.
- `eda.dmt_EditorControl.openDocument(uuid)` and `waitForDocumentReady()`; a PCB is activated with
  `activateDocument(pcbUuid + '@' + projectUuid)`.
- `eda.sch_Document.save()`, `eda.pcb_Document.save(pcbUuid)`, `eda.pcb_Document.importChanges(pcbUuid, true)`.

## PCB primitives (unit: mil, Y up)
- `eda.pcb_PrimitiveComponent`: `getAllPrimitiveId()`, `get(id)` (designator, layer, x, y, rotation),
  `getAllPinsByPrimitiveId(id)` (padNumber, net, x, y, layer, rotation, pad = [shape, w, h…], hole),
  `modify(id, {x, y, rotation, layer})`.
- `eda.pcb_PrimitiveLine.create(net, layer, x1, y1, x2, y2, width)`, `.get(id)`, `.delete([ids])`.
- `eda.pcb_PrimitiveVia.create(net, x, y, holeDia, dia)`.
- `eda.pcb_PrimitivePour` (outline, `rebuildCopperRegion()`) and `eda.pcb_PrimitivePoured` (fills:
  `pourFills[].path.complexPolygon`, rings in units of 10 mil with `'L'` / `'ARC'` markers).
- `eda.pcb_PrimitiveRegion.create(layer, eda.pcb_MathPolygon.createPolygon(poly), [9], name, 2, false)`
  creates a rule region.

## Rules and DRC
- `eda.pcb_Drc.check(true, false, true)` → `[{name: category, list: [{name: net/rule, list: [errors]}]}]`.
- `getNetRules()`, `getRegionRules()` / `overwriteRegionRules(list)`,
  `getCurrentRuleConfiguration()` / `overwriteCurrentRuleConfiguration(cfg)`. Track-width classes live
  in `config.Physics.Track[name].form.data['1'] = {minValue, defaultValue, maxValue}` (mm).

## Manufacturing
- `eda.pcb_ManufactureData.getGerberFile(name)` → File (zip). `getBomFile()` and `getPickAndPlaceFile()`
  → xlsx. `getNetlistFile()` → `.enet` JSON (also `eda.sch_ManufactureData.getNetlistFile()`).
  `.enet`: `components` is a dict keyed by uid; `components[uid].pinInfoMap[pin].net`, `props.Designator`.
- Do **not** use `eda.sch_Netlist.getNetlist()`. It opens a dialog and never returns.
