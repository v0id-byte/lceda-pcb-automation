---
name: lceda-pcb-automation
description: Automate PCB layout work in LCEDA Pro / EasyEDA Pro / 嘉立创EDA专业版 4.x through its CLI. Covers opening a project, exporting real board geometry, placement search, grid A* autorouting with clearance pre-checks, pour rebuild and floating-ground repair, DRC, schematic-vs-PCB netlist verification, track width / neck / angle audits, and Gerber/BOM/CPL export with an independent CAM check. Use when asked to route, fix DRC, verify or ship a board designed in LCEDA/EasyEDA Pro.
---

# LCEDA Pro PCB automation

A toolkit plus a discipline. The toolkit drives LCEDA Pro 4.x through its CLI (`LCEDA-Pro invoke`).
The discipline is what makes it safe: **every edit is planned off-board, pre-checked, committed,
and then verified by a different path** (DRC, netlist diff, re-exported geometry, Gerbers).

> Schematic-side editing (net ports, adding parts, part swaps) is covered by the companion
> [`easyeda-pro`](https://github.com/v0id-byte/easyeda-pro-claude-skill) skill. This skill starts once the schematic is right and the PCB is being laid out.

## 0. Ground rules

1. **Back up the `.eprj2` before every batch** (it is SQLite with an encrypted blob: no partial recovery).
   Keep numbered snapshots: `00-base`, `01-…`, `04-drc0`.
2. **Never relax a DRC rule to make an error go away.** A justified exception (e.g. 8 mil branches
   that only feed pull-ups) gets a *region-scoped* rule (`js/region_track_rule.js`) and a written reason.
3. `invoke` returning `ok:true` only means the JS ran. Check results by re-reading: DRC, netlist,
   `refresh.py` geometry, file mtime after save.
4. **Rehearse on a copy.** Copy the `.eprj2`, open the copy (`eda.sh open copy.eprj2 headless`) and
   run the planned batch there first. Then repeat it on the real file.
5. All tools print board coordinates in **mm, y pointing down from the board's top edge**. Internally
   everything is LCEDA mil (`cfg.X(mm)`, `cfg.Y(mm)`, `cfg.mm(X, Y)` convert).

## 1. Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export LCEDA_WORK=~/pcb-work/myboard          # holds project.json, sid.txt, geom.json, poured.json
bin/eda.sh open ~/Documents/LCEDA-Pro/projects/myboard.eprj2   # opens a window, saves sid.txt
bin/eda.sh js/discover.js                      # project uuid, schematic pages, PCB doc ids
# ... work ...
bin/eda.sh close destroy                       # end the session and close its window (pitfalls #22)
```

`open` creates a new session per call, and a copy of a project gets a **new project uuid**: run
`discover.js` again for every file you open. `pcb()` opens the PCB document if the session has not
opened it yet (pitfalls #21).

Write `$LCEDA_WORK/project.json` from `examples/project.example.json`:
- `project_uuid`, `pcb_doc`, `sch_pages` from discover.
- `board.origin_mil`: the LCEDA coordinate of the board's top-left corner. `size_mm`: the outline size.
  `keepouts_mm`: rectangles with no copper at all (antenna area). `slots_mm`: NPTH pegs as `[x, y, r]`.
- `layers.copper`: copper layer ids (1 top, 2 bottom, 15… inner). `planes`: inner layers flooded with
  ground. `route`: default routing layers; keep plane layers out unless you must, because every track
  on a plane layer cuts the plane.
- `via`: `default_mil` = [hole, diameter], and `nets` for nets whose rule class needs bigger vias
  (`net_rules.js` shows the via class per net; the router and every commit use the per-net size).
- `clearance`: base rule, plus the larger rule and the list of nets it applies to. Read them with
  `bin/eda.sh js/net_rules.js`. Track-to-track and track-to-via can differ per class, so check the matrix.

`bin/eda.sh file.js [timeout_s] [args_json]` prepends `CFG`, `ARGS` and `pcb()` (activate the PCB)
to the script. `lib/eda.py` wraps the same thing for Python.

## 2. Baseline (before touching anything)

```bash
bin/eda.sh js/netlist_sch.js > base_sch.json
bin/eda.sh js/netlist_pcb.js > base_pcb.json
python tools/netdiff.py base_sch.json base_pcb.json      # must show no changes: sch == pcb
python tools/refresh.py --rebuild                         # geom.json + poured.json
bin/eda.sh js/drc.js 600 | head -c 2000                   # note pre-existing errors
python tools/islands.py; python tools/widths.py; python tools/angles.py
```

## 3. Schematic changes reach the PCB

After schematic edits: `bin/eda.sh js/import_changes.js` **twice**, then diff the netlists:
`netdiff.py base_sch.json new_sch.json` must list exactly the intended changes, and
`netdiff.py new_sch.json new_pcb.json` must list none. Renamed nets leave tracks under the old
or new name. Find them in `geom.json` and rip them with `js/rip_move.js`.

## 4. Placement

- `tools/fit.py spec.json` searches legal positions and rotations near a target point. It respects
  pads of other nets, courtyards (pad bounding boxes + margin), board edge and keepouts, and places parts
  one after another. Commit the result with `js/rip_move.js` and `ARGS {"mv": {"R8": [x, y, rot, layer]}}`.
- Decoupling caps go first, as close as the pins allow. Check the pin-to-cap path length, not just
  the centre distance.
- Moving a part to the other side mirrors its pads. Re-read the pad positions that `rip_move.js` returns.
- **Parts must be separated by their footprint outlines (pads + silkscreen), not by pad clearance.**
  DRC only checks copper. `tools/courtyard.py` lists overlapping footprints, `tools/unoverlap.py`
  nudges a small part clear (dragging its track ends), and `place_route.py` keeps candidates
  outside other parts' outlines (`fit.py` only uses pad extents + a margin). Run `courtyard.py` after every placement batch.
  `tools/fix_overlaps.py` works through the overlap list automatically and reports what it could not move.
- **Vias whose drill lands in an SMD pad** pass DRC (same net) but wick solder away during reflow.
  `tools/vias_in_pads.py --skip <thermal-pad parts>` lists them (`--geom old/geom.json` for a baseline
  to diff against); `tools/dogbone.py PAD --commit` moves the via just outside the pad and joins it
  with a stub. Whatever cannot move needs the fab's via-in-pad process (filled and capped) on the order.
- A footprint with NPTH pegs or slots (some tactile switches, connectors) drills through every layer.
  Pass them to `place_route.py --holes dx,dy,dia;...`; read them from the footprint with
  `openLibraryDocument` (see `references/api-notes.md`).

## 5. Routing loop

```bash
python tools/route_net.py NET --w 8                 # dry run: prints the path in mm + conflicts
python tools/route_net.py NET --w 8 --commit --all   # commit + refresh, repeat until one island
python tools/route_zone.py NET x0,y0,x1,y1 --commit # dense area: search only inside the zone
python tools/manual.py plan.json [--commit]         # hand-drawn copper, same clearance pre-check
```

- The router is a grid A* (2.5 mil grid) on the real exported geometry. Every other-net object is
  inflated by the clearance rule. The ground pour is never an obstacle, because it re-pours around new
  copper. Vias honour hole-to-hole spacing and are never placed in a pad.
- Dense block with several nets? `python tools/route_order.py N1 N2 N3 [--rip] --commit` tries every
  order in memory instead of committing a greedy sequence that walls itself in.
- Route the nets that need the most room first: power widths from the rule table, then
  length-critical nets, then everything else. Refresh after every commit; the next route must see the
  previous one.
- **End every segment exactly on a pad centre, a via centre, or another segment's end point.** See
  pitfalls #1.

## 6. Pours and ground

```bash
bin/eda.sh js/add_pour.js 120 '{"net": "GND", "layers": [1, 2]}'   # board-sized pour, if there is none
python tools/refresh.py --rebuild
python tools/islands.py GND                 # floating ground pads after the re-pour
python tools/render.py x0,y0,x1,y1 15,16 out.png --islands GND   # red = cut-off plane pocket
python tools/gnd_fix.py C12.2 U3.4 [--commit]
python tools/stitch.py VM --near 29.5,9.6 --via 20,36   # parallel vias where a net has copper on both layers
python tools/stitch.py GND --in-pad U10.41 --n 9          # thermal vias inside an exposed pad
```

Floating ground almost always has one of these causes:
- A plane pocket fenced in by signal tracks on the inner layers. **Move a fencing track**; adding
  vias inside the pocket doesn't help.
- A pad boxed in by neighbours. Rotate the part so its ground pad faces open pour.
- A track end that doesn't land exactly on the pad.

## 7. Verification gates (all must pass, in this order)

| Gate | Command | Pass |
|---|---|---|
| Pours current | `refresh.py --rebuild` | — |
| DRC, rules untouched | `eda.sh js/drc.js 600` | `"sum": {}` |
| Schematic == PCB | `netdiff.py sch.json pcb.json` | no changes, no single-pin nets |
| Intent | `netdiff.py base_sch.json sch.json` | only the planned changes |
| Footprints apart | `courtyard.py` (`--body --gap 0.1` if no silkscreen) | no overlapping pairs: parts on one side are separated by their **silkscreen outlines** (or bodies), not just by pad clearance (pitfalls #27) |
| Vias out of pads | `vias_in_pads.py --skip U1,...` | no new `HOLE` rows, or via-in-pad ordered (pitfalls #35) |
| Connectivity | `islands.py`, `stubs.py` | only the known false splits (see pitfalls #6); every dangling end explained |
| Widths | `widths.py`, `necks.py NET:mil` | power nets meet their current; necks only at pins |
| Corners | `angles.py` | no acute corners from your own routing |
| Saved | `eda.sh js/save_all.js`, `eda.sh close destroy`, reopen, re-read one change | the change is there after reopening (pitfalls #8) |
| CAM | `cam_export.py OUT [--no-silk]`, `camcheck.py OUT/gerber`, `assembly_drawing.py OUT/assembly.pdf` | no copper at the edge, hole spacing and rings OK, no new mask dams < 0.1 mm (pitfalls #34); assembly drawing readable, polarity marked |

Then snapshot the `.eprj2` together with `drc.json`, both netlists and `geom.json`, and have an
**independent reviewer** (a fresh agent) check the exported data read-only: datasheet limits,
decoupling, current paths, BOM stock and price, assembly sides.

## 8. Files

- `bin/eda.sh`: CLI wrapper (open / sessions / close / run JS).
- `js/`: one job per script (discover, export_geom, export_poured, add_pour, rebuild_pours, drc, save_all,
  import_changes, netlist_sch, netlist_pcb, gerber, bom_cpl, rip_move, net_rules, region_track_rule).
- `lib/`: `cfg`, `pcbgeo` (geometry loader + islands), `router` (A*), `check` (clearance), `eda`
  (run/commit), `camgeo` (Gerber parser).
- `tools/`: the commands above, plus `courtyard.py` / `unoverlap.py` / `fix_overlaps.py` (footprint overlaps), `vias_in_pads.py` / `dogbone.py` (vias in pads), `assembly_drawing.py`, `route_order.py` (try net orders in memory), `place_route.py`
  (placement that must also route), `stubs.py` (dangling track ends), `move_via.py` / `move_part.py` (nudge copper and drag attached
  track ends, clearance-checked) for clearing a corridor.
- `examples/ldo-breakout/`: a complete 2-layer run (`.eprj3` before/after + walkthrough). Use it to
  check a new machine or editor version: the walkthrough must end at DRC 0.
- `references/pitfalls.md`: read it before the first commit on a new board.
- `references/api-notes.md`: the LCEDA API calls used here, with their quirks.
