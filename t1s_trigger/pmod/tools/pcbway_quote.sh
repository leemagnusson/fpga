#!/usr/bin/env bash
# Upload the board to PCBWay and print a link to a pre-filled instant quote.
#   tools/pcbway_quote.sh            bare boards: out/t1s_tap_gerbers.zip
#   tools/pcbway_quote.sh assembly   boards + assembly: out/t1s_tap_assembly.zip (gerbers,
#                                    PCBWay_bom.csv, PCBWay_positions.csv, plugin layout)
# Uses the endpoint PCBWay's official KiCad plugin posts to; no account is needed for the
# upload. Log in on the page that opens to save the quote or order. Run tools/build.sh first.
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-pcb}" in
  pcb)      zip=out/t1s_tap_gerbers.zip ;;
  assembly) zip=out/t1s_tap_assembly.zip ;;
  *) echo "usage: $0 [pcb|assembly]" >&2; exit 2 ;;
esac
[ -f "$zip" ] || { echo "missing $zip, run tools/build.sh" >&2; exit 1; }
rsp=$(curl -sS -L -A "Mozilla/5.0 (X11; Linux x86_64) KiCad-PCBWay-plugin" \
        -F "upload[file]=@$zip;filename=t1s_tap.zip" \
        -F boardWidth=20.1 -F boardHeight=40.1 -F boardLayer=2 \
        https://www.pcbway.com/Common/KiCadUpFile/)
python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["state"]); print(r["redirect"])' <<<"$rsp"
cat <<'TXT'
PCB parameters to check on the page: 2 layers, 20 x 40 mm, 1.6 mm FR-4, 1 oz copper,
min track/space 0.25 mm, min hole 0.3 mm, HASL or ENIG, no impedance control, no castellations.
TXT
if [ "${1:-pcb}" = assembly ]; then cat <<'TXT'
Assembly: tick "PCB Assembly" on the quote page, single side (all parts on top), 16 parts
in 13 BOM lines, 12 SMT + 4 THT, parts sourced by PCBWay from the MPNs in PCBWay_bom.csv,
no DNP, no sensitive parts. JP1 and TP1 are bare copper, nothing to place.
TXT
fi
