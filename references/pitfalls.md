# Pitfalls that cost hours (LCEDA Pro 4.1, found on real boards)

1. **DRC connectivity is endpoint-based.** If a track end stops in the middle of another segment, it is
   *not* connected, even though the copper overlaps. The same applies to a track that just passes over a
   via. `pcbgeo.islands()` (geometric overlap) will say "connected" and DRC will report a Connection Error.
   The fix is to split the segment, or to end every segment exactly on a pad centre, a via centre or
   another segment's end point. To find the offender, list the net's tracks with exact mil coordinates
   from `geom.json` and compare the end points.

2. **Inner-plane pockets.** If you route signals on the ground-plane layers, the tracks can fence in a
   piece of the plane. Ground vias that land in that pocket connect to nothing. Symptoms: several ground
   pads in one area all float, and `gnd_fix.py` reports NOFIT. Diagnose with
   `render.py … --islands GND` (red = pocket), then move one of the fencing tracks.

3. **A schematic pin dropped on an existing wire merges the two nets silently.** Example: a divider
   resistor placed on an SPI wire merged `VBUS_SENSE` into `SPI_MISO`. Place new parts in empty space,
   wire them, then diff the netlist.

4. **`importChanges` (Update PCB) needs two passes**, and net renames leave old tracks behind under the
   new name, or orphaned under the old one. Rip and re-route them.

5. **Side swaps mirror pads.** A part moved bottom → top (or back) comes out mirrored, and rotation on
   the bottom side runs counter-clockwise in LCEDA's Y-up frame. A +180° correction is often needed.
   Re-read the pad positions after every move.

6. **Known false splits in the geometric island check:** pour fills stop short of same-net pads, because
   direct-connect spokes are not part of the fill data. `POUR_PAD_TOL` bridges most of these, but some
   nets can still show up split (typically pads connected only by pour). DRC is the authority. Keep a
   list of the false splits for each board.

7. **Rule classes are a matrix.** A "strong" class can be 8 mil track-to-track but still only 6 mil
   track-to-via and via-to-via. Read the whole table before trusting a tool's clearance setting.

8. **`save()` can return true without writing, and the mtime is not proof either.** LCEDA 4.1 also
   writes edits into the `.eprj2` history as they are made, so a correct save may leave the mtime
   unchanged (nothing new to write). Run `js/save_all.js`, then prove persistence the only reliable way:
   `eda.sh close destroy`, reopen the file in a new session, re-read the change. Back up first.

9. **`ok:true` from `invoke` means only that the script ran.** Validate inside the script (throw on
   failure), or re-read afterwards.

10. **Pours go stale.** Any copper edit leaves the poured copper out of date until
    `rebuild_pours.js`. DRC, `export_poured.js` and Gerbers all need a rebuild first.

11. **The Gerber zip stores Chinese member names in GBK without the UTF-8 flag.** Re-decode them with
    `cp437 → gbk` (`cam_export.py` does this).

12. **Pad rotation units changed between builds:** older API builds reported radians, 4.x reports
    degrees. `pcbgeo.pad_shape` handles both.

13. **Never relax a rule to clear DRC.** If a neck is genuinely fine (a logic-supply branch carrying
    µA–mA), add a region-scoped track rule and record why. Board-wide relaxations hide the next real
    defect.

14. **Fewer parts is sometimes the fix.** When a cap really can't be routed at the required width, check
    whether the remaining bulk and decoupling already cover it, and if so drop the part rather than
    choking the route. Write down the reasoning.

15. **Greedy single-net routing is order-sensitive.** In a dense block the first net routed walls in the
    next (e.g. a buffer's output route wrapping around a neighbouring pin). Use `route_order.py`: it tries
    every order in memory and commits the shortest complete one. Route inputs and the most constrained
    pin first; check total length afterwards, because a "successful" route can be a 50 mm detour.

16. **`fit.py` legality ≠ routability.** A part can fit in a pocket nothing can reach. Use
    `place_route.py`, which only accepts positions where every pad actually routes.

17. **Pour priority: 1 = highest.** A new pour drawn over an existing ground pour with a larger number
    fills nothing. A same-net pour over a power neck flows around the signal vias that pin a track to
    25 mil and can more than double the cross-section without moving anything. Measure it afterwards
    with the Gerber (`camcheck.py` geometry), not only the API geometry. In one case the API-side
    estimate said 45 mil while the Gerber measured 32.

18. **Moving a part between sides mirrors it differently from a naive prediction.** After a move,
    compare the returned pad positions with the plan. For 2-pad parts, re-rotate 180° if they came out
    swapped. Otherwise a pad ends up on another net's copper.

19. **DNP parts still have copper, and usually stencil paste.** Keep their pads away from THT joints
    of other nets as well. The CAM check reports mask dams < 0.1 mm that the fab will remove.

20. **Arcs are real geometry.** Pour fills use `'ARC', sweep_deg, x, y` segments (positive sweep = centre
    on the left of the chord), and boards contain arc tracks (`pcb_PrimitiveArc`). Treating arcs as
    straight chords overstates copper and invents false splits. `pcbgeo` now interpolates both.

21. **A freshly opened project has no PCB document open.** Every `pcb_*` call then fails with
    `指定的主题消息在对应的画布内没有相关订阅` ("no subscription for this topic in the canvas") or a
    `null` result. `pcb()` in `bin/eda.sh` opens the document before activating it. Call it first in
    any script you write.

22. **Headless and CLI windows leak.** Every `open` holds a full editor renderer until it is closed.
    End scripted runs with `eda.sh close destroy`. Never close a session the user opened in the GUI.

23. **A tool that reports "dangling" must probe with the real copper.** A track end is a round cap of
    radius w/2, not a point. Probing the bare point flags ends that stop a few mil short of a via or
    a pour. `stubs.py` uses the cap.

24. **`.eprj3` folder projects sync both ways, and every open gets a new project uuid.** The editor
    writes edits straight back into the folder, so open a copy, never a checked-in project. The new
    uuid breaks `pcb()` (`activateDocument(pcb@project)`). `eda.sh open` writes the current uuid
    into `project.json`.

25. **Some library lookups come back empty.** In 4.1.78 `lib_Device.getByLcscIds([...])` returned
    `[]` for parts that exist. `lib_Device.search('C6186', …)` finds them: keep the hit whose
    `supplierId` matches exactly, then `lib_Device.get(uuid)` for the real `libraryUuid`.

26. **New schematic net ports hide their name, and up/down rotations are easy to get backwards.**
    `createNetPort` leaves the `Name` attribute at `valueVisible: false`. Set it with
    `sch_PrimitiveAttribute.modify(id, {valueVisible: true})`. The schematic's Y axis points up, and
    a port points outward with rotation 180 on a left pin, 0 on a right pin, 270 on a top pin and
    90 on a bottom pin. Check by exporting `sch_ManufactureData.getPngFile()` and looking at it.

27. **DRC passes boards whose parts sit on top of each other.** The rules only cover copper, so two
    footprints can overlap by millimetres as long as their pads keep clearance. On one board, 30
    pairs of silkscreen outlines overlapped at DRC 0, including a 1206 cap inside a 12 mm inductor's
    outline. Check footprint outlines (`courtyard.py`, from `pcb_Primitive.getPrimitivesBBox`, which
    covers pads + footprint silkscreen but not the designator text) as a separate gate. If the board
    ships without silkscreen, bodies are what must not collide: `courtyard.py --body` estimates them
    from the footprint names. On that board 29 of the 30 overlapping pairs turned out to be
    silkscreen-only, and one (a 0603 under an inductor) was a real body collision.

28. **Footprint pegs are holes through the whole board.** A 4×3 mm tactile switch (`…-EH` variant)
    has two 0.9 mm NPTH pegs. Placed on the bottom under an ESP32 module, they drilled through the
    module's pads on the top layer. DRC reports this as `Slot Region to …` errors. The exported board
    geometry does not contain footprint holes, so read the footprint (`openLibraryDocument`, layer 12
    fills) and give them to `place_route.py --holes`, or pick the variant without pegs.

29. **DRC error positions are in units of 10 mil** (`errData.position`), not mil: multiply by 10
    before converting to board mm.

30. **A swap check that only covers the pads you routed is no swap check.** `place_route.py` used to
    verify only the pads it had routed. When a part's pads were already connected by copper (nothing
    to route), a mirrored 2-pad placement slipped through and EN.1 landed on the GND side. Compare
    every pad with the plan.

31. **`pcb_ManufactureData.getPdfFile` can hang an interactive session** (it may open an export dialog in
    the user's window) and `invoke` times out after its budget. Do not call it on the user's GUI
    session. `tools/assembly_drawing.py` draws the assembly / designator drawing from exported data.

32. **One width for every pad of a moved part is wrong.** A resistor between a 25 mil power net and
    an 8 mil signal got both routes at 25 mil, and DRC flagged the signal (class max 10 mil).
    Pass `place_route.py --widths NET:mil,...`. Vias likewise come from the net's rule class: list
    them in `project.json` `via.nets` (see `net_rules.js`).

33. **Forced moves that are reverted are not a perfect undo.** `move_part.py --force` there and back
    drags track ends twice; an end that left the pad on the way back stays where it was and can
    short to a neighbour. Re-run DRC after every revert (`unoverlap.py --drc` does) and re-check
    `stubs.py`.

34. **Clearing one overlap can thin a solder-mask dam.** Moving a 0603 0.3 mm towards its neighbour
    passed DRC (pad-pad 6 mil) and the body check, but left 0.094 mm of mask between the two parts'
    openings, below the fab's 0.1 mm minimum: the dam is dropped and two different nets share one
    opening. Only `camcheck.py` sees it (`*_mask_dam_lt0.1`). Compare its report with the previous
    export after every placement change.

35. **A via in a pad is invisible to DRC, and the PCB netlist has no pin names.** The via and the pad
    share a net, so nothing flags a drill hole inside a 0402 pad; `vias_in_pads.py` does, and
    `dogbone.py` moves what has room. Separately, `pcb_ManufactureData.getNetlistFile()` leaves every
    `pinInfoMap[*].name` empty; read pin names (K, A, ...) from the schematic netlist
    (`netlist_sch.js`), as `assembly_drawing.py` does for diode cathodes.

36. **A few small vias can double the board price.** JLC charges for any via with a hole under 0.3 mm
    or a diameter of 0.4 mm or less: TG155 material, four-wire via testing and a small-hole fee (about
    CNY 250 on a 4-layer prototype, more than the board itself). The base design carried twelve
    0.2/0.4 mm vias that DRC was happy with. `resize_vias.py` re-makes them at 12 mil / 0.45-0.5 mm.
    Three traps on the way: LCEDA stores mil with one decimal, so a 0.3 mm hole comes back as
    11.8 mil = 0.2997 mm (use 12 mil); deleting and re-creating a via orphans its teardrop, which DRC
    reports as a disconnected track and teardrop (resize in place with `pcb_PrimitiveVia.modify`, or
    delete the orphan by the id DRC gives); and the outer layers here use the 2 oz spacing table, where
    via-to-track is 0.152 mm, not the 0.114 mm of the 1 oz table. Check the drill file (`T..C0.30480`)
    before re-uploading.

37. **A pad created through the API breaks every pour rebuild.** Any board-level pad made with
    `pcb_PrimitivePad.create` (SMD or through-hole, plated or not, fiducial type or not, with or without
    mask/heat-welding settings) makes every later `rebuildCopperRegion()` throw "Cannot read properties
    of undefined (reading 'length')", so DRC and Gerbers run against stale copper. Delete the pad and the
    rebuild works again. Build NPTH holes as round slot regions (a `pcb_PrimitiveFill` on layer 12 with a
    `CIRCLE` polygon; it is exported as a drill, not a route) and fiducials as a copper disc plus a
    mask-layer disc (layers 5/6), as `edge_rails.py` does. Two more traps when finding those objects
    again: `getPrimitivesBBox()` returns nothing for slot regions, and a region's name is not kept, so
    read the polygon data instead. And a slot's round end leaves the board edge uncut for one radius:
    a tab keepout that stops at the tab lets the pour creep to 0.12 mm from the break line there.
