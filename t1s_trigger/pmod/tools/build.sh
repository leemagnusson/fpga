#!/usr/bin/env bash
# Regenerate the KiCad project from tools/netlist.py and run every check and export.
# Needs Docker (image kicad/kicad:9.0). Outputs land in out/.
set -euo pipefail
cd "$(dirname "$0")/.."
img=kicad/kicad:9.0
run() { docker run --rm -v "$PWD":/work -w /work "$img" "$@"; }   # image user is uid 1000 and owns the KiCad config
mkdir -p out/gerbers
run python3 tools/gen_sch.py
run python3 tools/gen_pcb.py 2>&1 | grep -v 'GetWidth called' || true
run kicad-cli sch erc --severity-all --format json -o out/erc.json t1s_tap.kicad_sch >/dev/null
run python3 tools/erc_summary.py out/erc.json
run kicad-cli pcb drc --severity-all --schematic-parity --format json -o out/drc.json t1s_tap.kicad_pcb >/dev/null
run python3 tools/drc_summary.py out/drc.json | grep -v 'silk_edge_clearance :'
run kicad-cli sch export netlist --format kicadxml -o out/netlist.xml t1s_tap.kicad_sch >/dev/null
run python3 tools/check_nets.py out/netlist.xml t1s_tap.kicad_pcb
run kicad-cli sch export pdf -o out/t1s_tap_sch.pdf t1s_tap.kicad_sch >/dev/null
run kicad-cli sch export svg -o out/ t1s_tap.kicad_sch >/dev/null
run kicad-cli sch export bom -o out/bom.csv --fields 'Reference,Value,Footprint,Manufacturer,MPN,Description,${QUANTITY}' --labels 'Ref,Value,Footprint,Manufacturer,MPN,Description,Qty' --group-by 'Value,Footprint' --exclude-dnp t1s_tap.kicad_sch >/dev/null
run kicad-cli pcb export svg --layers F.Cu,F.SilkS,F.Mask,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet -o out/pcb_top.svg t1s_tap.kicad_pcb >/dev/null
run kicad-cli pcb export svg --layers B.Cu,B.SilkS,B.Mask,Edge.Cuts --page-size-mode 2 --exclude-drawing-sheet --mirror -o out/pcb_bottom.svg t1s_tap.kicad_pcb >/dev/null
run kicad-cli pcb render --side top --zoom 1 -w 800 -h 1400 -o out/pcb_top.png t1s_tap.kicad_pcb >/dev/null 2>&1
run kicad-cli pcb render --side bottom --zoom 1 -w 800 -h 1400 -o out/pcb_bottom.png t1s_tap.kicad_pcb >/dev/null 2>&1
run kicad-cli pcb render --perspective --rotate "-35,0,25" --zoom 0.75 -w 1400 -h 1000 -o out/pcb_3d.png t1s_tap.kicad_pcb >/dev/null 2>&1
run kicad-cli pcb render --perspective --rotate "-60,0,200" --zoom 0.75 -w 1400 -h 1000 -o out/pcb_3d_rear.png t1s_tap.kicad_pcb >/dev/null 2>&1
run kicad-cli pcb export step --subst-models --no-dnp -o out/t1s_tap.step t1s_tap.kicad_pcb >/dev/null 2>&1
rm -f out/gerbers/*
run kicad-cli pcb export gerbers --layers F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,F.Paste,Edge.Cuts -o out/gerbers/ t1s_tap.kicad_pcb >/dev/null
run kicad-cli pcb export drill --format excellon --excellon-separate-th -o out/gerbers/ t1s_tap.kicad_pcb >/dev/null
rm -f out/t1s_tap_gerbers.zip && (cd out/gerbers && zip -q ../t1s_tap_gerbers.zip ./*)   # what fabs want uploaded
run kicad-cli pcb export pos --format csv --units mm --exclude-dnp -o out/positions.csv t1s_tap.kicad_pcb >/dev/null
python3 tools/pcbway_files.py out/positions.csv t1s_tap.kicad_pcb out/
echo "build done"; ls out out/gerbers
