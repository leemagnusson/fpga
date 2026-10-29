#!/usr/bin/env bash
# Open-source build checks for every project in this repo, using GHDL and
# Yosys. This is what .github/workflows/ci.yml runs on GitHub-hosted runners,
# where Vivado is not available. Run it locally with:
#
#   docker run --rm -v "$PWD":/src -w /src hdlc/ghdl:yosys ci/check.sh
#
# What it checks:
#   * bml1/ch4, bml1/ch5 : synthesise top.vhd (GHDL + Yosys) and top.v (Yosys)
#                          for Artix-7, which catches syntax/elaboration errors
#                          and non-synthesisable constructs.
#   * bml1/seg, bml1/seg2: synthesise the seven-segment designs the same way.
#   * can_timing         : run the can_sim testbench in GHDL.
#   * litefury_canfd     : analyse the glue RTL, and the CTU CAN FD core if the
#                          submodule is checked out (the PCIe IP needs Vivado).
#   * loose tutorial files in bml1/ : analyse only.
#
# Not checked (known broken scratch files):
#   * bml1/a.vhd            - missing semicolons, stray tokens
#   * src/bcd_counter.vhd   - "+" on std_logic_vector with no numeric package
#   * src/bcd_count4.vhd    - anonymous array type in a port declaration
set -euo pipefail
cd "$(dirname "$0")/.."

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

GHDL_FLAGS="--std=08 -fsynopsys --workdir=$WORK -P$WORK"

group() { echo "::group::$*"; }
endgroup() { echo "::endgroup::"; }

# Yosys is run quietly; the post-synthesis cell count is written to a file
# and printed so the log stays readable.
synth_stat() {
    local script=$1
    yosys -q -m ghdl -p "$script; tee -q -o $WORK/stat.txt stat"
    awk '/^=== top ===/{p=1} /^=== design hierarchy ===/{p=0} p' "$WORK/stat.txt"
}

group "Compile unisim stub library (ci/unisim_stub.vhd)"
ghdl -a $GHDL_FLAGS --work=unisim ci/unisim_stub.vhd
endgroup

for proj in bml1/ch4 bml1/ch5; do
    group "$proj: synthesise top.vhd for Artix-7 (GHDL + Yosys)"
    synth_stat "ghdl $GHDL_FLAGS $proj/top.vhd -e top; synth_xilinx -top top"
    endgroup

    group "$proj: synthesise top.v for Artix-7 (Yosys)"
    synth_stat "read_verilog $proj/top.v; synth_xilinx -top top"
    endgroup
done

# the seven-segment designs live beside their project directories
for src in bml1/seg.vhd bml1/seg2.vhd; do
    group "$src: synthesise for Artix-7 (GHDL + Yosys)"
    synth_stat "ghdl $GHDL_FLAGS $src -e top; synth_xilinx -top top"
    endgroup
done

group "can_timing: run can_sim testbench (GHDL)"
ghdl -a $GHDL_FLAGS can_timing/can_timing.vhd can_timing/can_sim.vhd
# One full message cycle is 15001 clocks at 66.6 ns, about 1 ms. Run two.
ghdl --elab-run $GHDL_FLAGS can_sim --stop-time=2ms --assert-level=error
echo "can_sim ran to 2 ms without errors"
endgroup

group "litefury_canfd: analyse glue logic (GHDL + Yosys)"
ghdl -a $GHDL_FLAGS litefury_canfd/rtl/misc_regs.vhd
yosys -q -p "read_verilog litefury_canfd/rtl/irq_bridge.v; synth_xilinx -top irq_bridge"
echo "ok: litefury_canfd/rtl"
endgroup

can_src=${CTU_CAN_FD_SRC:-third_party/CTU-CAN-FD/src}
if [ -f "$can_src/slf_rtl.yml" ]; then
    group "litefury_canfd: analyse CTU CAN FD core (GHDL, library ctu_can_fd_rtl)"
    files=$(sed -n 's/^ *- file: *//p' "$can_src/slf_rtl.yml" | sed "s#^#$can_src/#")
    # shellcheck disable=SC2086
    ghdl -a --std=08 --work=ctu_can_fd_rtl --workdir="$WORK" -P"$WORK" $files
    echo "ok: $(echo "$files" | wc -l) files"
    ghdl -a $GHDL_FLAGS litefury_canfd/rtl/can_wrap.vhd
    ghdl -e $GHDL_FLAGS can_wrap
    echo "ok: litefury_canfd/rtl/can_wrap.vhd elaborates against the core"
    yosys -q -p "read_verilog litefury_canfd/rtl/can_wrap_bd.v; proc"
    echo "ok: litefury_canfd/rtl/can_wrap_bd.v parses"
    endgroup
else
    echo "note: CTU CAN FD core not present ($can_src); run 'git submodule update --init' to check it too"
fi

group "bml1 loose tutorial sources: analyse only"
for f in bml1/top2.v bml1/top3.v; do
    yosys -q -p "read_verilog $f; synth_xilinx -top top"
    echo "ok: $f"
done
endgroup

echo "All checks passed."
