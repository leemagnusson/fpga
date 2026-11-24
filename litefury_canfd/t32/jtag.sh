#!/bin/sh
# JTAG for the artix_m2_canfd card with a Lauterbach debugger (tested with a
# uTrace and TRACE32 for Arm; see ../README.md for the wiring).
#
#   t32/jtag.sh status              IDCODE and DONE
#   t32/jtag.sh load top.bit        configure the FPGA (volatile)
#   t32/jtag.sh flash golden.bin    write a .bin to flash address 0 (or a .mcs), verify, boot from it;
#                                   takes about two minutes
#   t32/jtag.sh reboot              reconfigure the FPGA from flash
#   t32/jtag.sh temp                FPGA temperature and core/auxiliary supply voltages (on-chip monitor)
#
# Environment: T32SYS (TRACE32 directory, default: found from t32marm on PATH),
# T32EXE (PowerView executable, default t32marm: use the one your licence is for).
set -e
here=$(cd "$(dirname "$0")" && pwd)
exe=${T32EXE:-t32marm}
if [ -z "${T32SYS:-}" ]; then
    bin=$(command -v "$exe") || { echo "jtag.sh: $exe not found; set T32SYS" >&2; exit 2; }
    T32SYS=$(cd "$(dirname "$(readlink -f "$bin")")/../.." && pwd)
else
    bin=$T32SYS/bin/pc_linux64/$exe
fi
mode=${1:?usage: jtag.sh status | load <bit> | flash <bin|mcs> | reboot | temp}
file=${2:+$(readlink -f "$2")}
case $mode in
    status|reboot) ;;
    temp) mode=xadc ;;
    load|flash) [ -f "$file" ] || { echo "jtag.sh: no such file: $2" >&2; exit 2; } ;;
    *) echo "jtag.sh: unknown command $mode" >&2; exit 2 ;;
esac
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if [ "$mode" = flash ]; then
    # Vivado leaves its hw_server running; stop it again unless one was running before.
    had_server=$(pgrep -x hw_server || true)
    (cd "$tmp" && "$here/../../ci/vivado.sh" -mode batch -nojournal -log "$tmp/gen_svf.log" \
        -source "$here/gen_svf.tcl" -tclargs "$file" "$tmp/flash.svf" > "$tmp/vivado.out" 2>&1) \
        || { tail -20 "$tmp/vivado.out" >&2; echo "jtag.sh: Vivado could not write the SVF file" >&2; exit 1; }
    [ -n "$had_server" ] || pkill -x hw_server || true
    [ -n "$had_server" ] || pkill -x cs_server || true
    mode=svf
    file=$tmp/flash.svf
    echo "playing $(du -h "$file" | cut -f1) of SVF, about two minutes ..."
fi

cat > "$tmp/config.t32" <<CFG
OS=
SYS=$T32SYS
TMP=$tmp

PBI=
USB

SCREEN=OFF
CFG
rc=0
"$bin" -c "$tmp/config.t32" -s "$here/jtag.cmm" "$mode" "$tmp/jtag.log" "$file" > "$tmp/t32.out" 2>&1 || rc=$?
[ -f "$tmp/jtag.log" ] || { cat "$tmp/t32.out" >&2; echo "jtag.sh: TRACE32 did not run the script (is the debugger connected and not in use?)" >&2; exit 1; }
if [ "$mode" = xadc ]; then
    # UG480: temperature = code * 503.975 / 4096 - 273.15 C, supplies = code * 3 V / 4096 (12-bit code in bits 15:4)
    grep -v '^xadc ' "$tmp/jtag.log" | grep -v '^DONE='
    awk '$1 == "xadc" { v[$2 + 0] = int($3 / 16) }
         function t(c) { return c * 503.975 / 4096 - 273.15 }
         END { if (!(0 in v)) exit 1
               printf "temperature %.1f C (min %.1f, max %.1f since configuration)\n", t(v[0]), t(v[36]), t(v[32])
               printf "VCCINT %.3f V (min %.3f, max %.3f)\n", v[1] * 3 / 4096, v[37] * 3 / 4096, v[33] * 3 / 4096
               printf "VCCAUX %.3f V (min %.3f, max %.3f)\n", v[2] * 3 / 4096, v[38] * 3 / 4096, v[34] * 3 / 4096 }' "$tmp/jtag.log" || rc=1
else
    cat "$tmp/jtag.log"
fi
exit $rc
