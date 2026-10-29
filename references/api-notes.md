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
- `eda.dmt_Project.createProject(friendlyName, name)` → project uuid. It defaults to the `.eprj3`
  folder format under `~/Documents/LCEDA-Pro/projects/`. Open the result with `eda.sh open`.
  `eda.dmt_Board.createBoard()` adds a schematic + PCB pair. A newly opened project already has
  `Board1`. `dmt_Pcb.deletePcb(uuid)` / `dmt_Schematic.deleteSchematic(uuid)` remove orphans.
- `eda.dmt_Project.getCurrentProjectInfo()` → boards, schematic pages, PCB uuids.
- `eda.dmt_EditorControl.openDocument(uuid)` and `waitForDocumentReady()`; a PCB is activated with
  `activateDocument(pcbUuid + '@' + projectUuid)`.
- `eda.sch_Document.save()`, `eda.pcb_Document.save(pcbUuid)`, `eda.pcb_Document.importChanges(pcbUuid, true)`.

## PCB primitives (unit: mil, Y up)
- Board outline: `eda.pcb_PrimitivePolyline.create('', 11, eda.pcb_MathPolygon.createPolygon([x0, y0, 'L', x1, y0, …]), 10, false)`
  (layer 11 = board outline).
- Designators are `eda.pcb_PrimitiveAttribute` objects with `key == 'Designator'` and
  `parentPrimitiveId` = the component. `modify(id, {x, y, rotation, fontSize, alignMode: 5})`
  moves them off pads.
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

## Footprints and outlines
- `eda.pcb_Primitive.getPrimitivesBBox([componentId])` → `{minX, minY, maxX, maxY}`: pads + footprint
  silkscreen, without the designator text. Used by `js/comp_bbox.js`.
- A footprint's own primitives (NPTH pegs as layer-12 fills, body outline on layer 48, silkscreen on 3)
  can be read by opening it: `eda.dmt_EditorControl.openLibraryDocument(libraryUuid, '4', footprintUuid)`
  in a separate headless session, then `pcb_PrimitivePad.getAll()`, `pcb_PrimitiveFill.getAll()`,
  `pcb_PrimitivePolyline.getAll()`. Footprints embedded in a project (uuid `<pcb>_eNNN`) cannot be opened
  this way. `getPrimitiveBoardLine` returned `undefined` for component silkscreen.
- Schematic net-port names: `sch_PrimitiveAttribute.modify(attrId, {valueVisible: true})` on the port's
  `Name` attribute.

## Images
- Schematic: `eda.sch_ManufactureData.getPngFile()` / `getSvgFile()` (active page) → File.
- PCB canvas (also headless): `eda.dmt_EditorControl.zoomToAllPrimitives(tabId)`, then
  `getCurrentRenderedAreaImage(tabId)` → PNG Blob. `tabId` is `pcbUuid + '@' + projectUuid`.
  Return binary data from `invoke` as base64.

## Manufacturing
- `eda.pcb_ManufactureData.getGerberFile(name)` → File (zip). `getBomFile()` and `getPickAndPlaceFile()`
  → xlsx. `getNetlistFile()` → `.enet` JSON (also `eda.sch_ManufactureData.getNetlistFile()`).
  `.enet`: `components` is a dict keyed by uid; `components[uid].pinInfoMap[pin].net`, `props.Designator`.
- Do **not** use `eda.sch_Netlist.getNetlist()`. It opens a dialog and never returns.
