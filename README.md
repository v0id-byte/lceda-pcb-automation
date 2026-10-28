# lceda-pcb-automation

Scripted PCB layout for **LCEDA Pro / EasyEDA Pro / 嘉立创EDA专业版 4.x**. It drives the editor through
its official CLI (`LCEDA-Pro invoke`) and is built to be used by an AI coding agent as a skill
(`SKILL.md`), though every tool is a plain command-line script.

What it does:
- **Exports the real board** (pads, tracks, vias, computed pour copper) into shapely geometry.
- **Routes** with a grid A* router: other-net clearance by rule class, keepouts, via rules, ground
  pour treated as re-pourable. Every result is pre-checked before it is committed.
- **Places** parts by searching legal positions and rotations near a target.
- **Repairs floating ground** after a pour rebuild, and shows plane pockets in colour.
- **Verifies:** DRC, schematic-vs-PCB netlist diff, island check, track-width histogram, neck finder,
  sharp/acute corner finder.
- **Ships:** Gerber/BOM/CPL export plus an independent Gerber/drill check (edge clearance, hole
  spacing, annular ring, mask dams, silkscreen, paste).

It was developed while taking a 4-layer motor-controller board from schematic changes to DRC 0 and
fab files. The pitfalls in `references/pitfalls.md` are the ones that actually happened.

## Quick start

```bash
git clone https://github.com/v0id-byte/lceda-pcb-automation && cd lceda-pcb-automation
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export LCEDA_WORK=~/pcb-work/myboard && mkdir -p $LCEDA_WORK
bin/eda.sh open /path/to/board.eprj2
bin/eda.sh js/discover.js            # -> fill $LCEDA_WORK/project.json (see examples/)
.venv/bin/python tools/refresh.py --rebuild
bin/eda.sh js/drc.js 600
.venv/bin/python tools/route_net.py SOME_NET --w 8          # dry run
```

The full workflow and the verification gates are in [SKILL.md](SKILL.md).

To use it as a Claude Code skill, clone it into or symlink it to `~/.claude/skills/lceda-pcb-automation`.

## Requirements
- LCEDA Pro 4.1+ with the CLI. On macOS the default binary path is used; set `LCEDA_BIN` to override it.
- Python 3.10+ with shapely 2, numpy, matplotlib, openpyxl and gerbonara.

## Limits
- Boards are described by a rectangular outline plus keepout rectangles in `project.json`. Irregular
  outlines need `pcbgeo.OUTLINE` replaced.
- The router is single-net and greedy: good for completing and repairing a layout, not for
  length-matched or impedance-controlled buses.
- LCEDA's internal formats (`.enet`, pour fill paths) have no stability promise. Re-check after
  editor upgrades.

## License
MIT
