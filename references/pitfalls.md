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

8. **`save()` can return true without writing.** Save every page and the PCB (`js/save_all.js`) twice,
   then check the `.eprj2` mtime. Back up first.

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
