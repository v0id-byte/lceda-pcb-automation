# Example: USB-C → 3.3 V LDO breakout (2 layers, 30 × 20 mm)

**English** | [简体中文](README.zh-CN.md)

A small board that walks through the whole toolkit: from a placed but unrouted board to DRC 0 and
fab files, using only the command line. The whole walkthrough runs in about 1.5 minutes.

| | |
|---|---|
| Parts | USB-C 6P receptacle, 2 × 5.1 kΩ CC pull-downs, AMS1117-3.3, 10 µF / 22 µF / 100 nF, LED + 1 kΩ, 1×3 header |
| Nets | `VBUS`, `+3V3`, `GND`, `CC1`, `CC2`, `LED_A` |
| Board | 2 layers, 30 × 20 mm, outline origin at (0, 0) mil |
| Folders | `start/`: parts placed, no copper. `routed/`: the finished board, same steps as below. |

Both projects are in LCEDA Pro's folder format (`.eprj3`): JSON lines, readable in a diff.
This is a demonstration board. It has passed DRC and the CAM check below, but it has not been built
and tested.

![schematic](images/schematic.png)

| Start: placed, ratsnest only | Routed: DRC 0, GND poured on both layers |
|---|---|
| ![placed](images/placed.png) | ![routed](images/routed.png) |

Both screenshots are the real LCEDA Pro canvas, captured with
`eda.dmt_EditorControl.getCurrentRenderedAreaImage()`.

## Walkthrough

Run from the repository root, after the [setup](../../README.md#quick-start). LCEDA Pro keeps a
`.eprj3` folder in two-way sync with the editor, so **work on a copy**, never in the repository.

```bash
export LCEDA_WORK=~/pcb-work/ldo && mkdir -p $LCEDA_WORK
cp -R examples/ldo-breakout/start/ldo-breakout $LCEDA_WORK/
cp examples/ldo-breakout/project.json $LCEDA_WORK/
PY=.venv/bin/python

# 1. Open and take a baseline. `open` writes the session id and the project uuid.
bin/eda.sh open $LCEDA_WORK/ldo-breakout/ldo-breakout.eprj3 headless
bin/eda.sh js/netlist_sch.js > $LCEDA_WORK/sch.json
bin/eda.sh js/netlist_pcb.js > $LCEDA_WORK/pcb.json
$PY tools/netdiff.py $LCEDA_WORK/sch.json $LCEDA_WORK/pcb.json   # 10 parts, no changes
$PY tools/refresh.py
$PY tools/islands.py                                              # every net is still in pieces

# 2. Route. Power first and wide, then the signals.
$PY tools/route_net.py VBUS --w 20                                # dry run: path in mm + conflicts
for net in VBUS +3V3; do $PY tools/route_net.py $net --w 20 --commit --all; done
for net in CC1 CC2 LED_A; do $PY tools/route_net.py $net --w 10 --commit --all; done

# 3. Ground: pour both layers, then stitch them together around the edge.
bin/eda.sh js/add_pour.js 120 '{"net": "GND", "layers": [1, 2], "margin_mm": 0.3}'
$PY tools/refresh.py --rebuild
for p in 9,2.5 15,2.5 20,2.5 28.5,2.5 28.5,5 2.5,17.5 9,17.5 15,17.5 20,17.5 28.5,17.5; do
  $PY tools/stitch.py GND --n 1 --near $p --r 1.5 --via 12,24 --commit && $PY tools/refresh.py
done
$PY tools/refresh.py --rebuild
$PY tools/islands.py                                              # TOTAL missing links: 0

# 4. Verify.
bin/eda.sh js/drc.js 600 | head -c 200                            # "sum": {}
bin/eda.sh js/netlist_pcb.js > $LCEDA_WORK/pcb2.json
$PY tools/netdiff.py $LCEDA_WORK/sch.json $LCEDA_WORK/pcb2.json  # still no changes
$PY tools/stubs.py && $PY tools/angles.py && $PY tools/widths.py VBUS +3V3

# 5. Fab files and an independent Gerber check.
$PY tools/cam_export.py $LCEDA_WORK/cam --name ldo-breakout
$PY tools/camcheck.py $LCEDA_WORK/cam/gerber > /dev/null && cat $LCEDA_WORK/cam/gerber_report.json

# 6. Save, close, and prove it was saved by reopening.
bin/eda.sh js/save_all.js
bin/eda.sh close destroy
bin/eda.sh open $LCEDA_WORK/ldo-breakout/ldo-breakout.eprj3 headless
bin/eda.sh js/drc.js 600 | head -c 200
bin/eda.sh close destroy
```

## What to expect

- **Routing:** VBUS and +3V3 come out at 20 mil, CC1/CC2/LED_A at 10 mil. The VBUS run to the header
  drops to the bottom layer through one via. Each commit was pre-checked for clearance.
- **Connectivity:** the first `islands.py` reports 25 missing links (13 of them GND). After routing
  and the pour it reports 0.
- **DRC:** `{}` with the editor's default rules, which were not changed.
- **CAM check:** no copper at the edge, no hole-spacing or annular-ring problems, no silkscreen on
  pads.
  - `top_silk_off_board` shows about 0.46 mm² at x ≈ 0. That is the USB-C outline sitting on the
    board edge, and the fab clips it.
  - `top_paste_off_copper` is a few hundredths of a mm² per pad. The library footprints' paste
    openings are slightly larger than, or offset from, their copper.

Your routes can differ slightly from `routed/` if the editor or library footprints change. The
checks are what matter.

## How the example was made

The project itself was also scripted:
1. `dmt_Project.createProject` created the project.
2. Parts came from the JLC library (`lib_Device.search` by LCSC number).
3. The schematic was built from net flags and net ports at each pin, then pushed to the PCB with
   `js/import_changes.js` (twice).
4. `tools/fit.py` placed the parts near target points.
5. Designators were moved off the pads.

See [`SKILL.md`](../../SKILL.md) for the general workflow.
