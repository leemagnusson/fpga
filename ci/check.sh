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
#   * can_timing         : run the can_sim testbench in GHDL.
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

group "can_timing: run can_sim testbench (GHDL)"
ghdl -a $GHDL_FLAGS can_timing/can_timing.vhd can_timing/can_sim.vhd
# One full message cycle is 15001 clocks at 66.6 ns, about 1 ms. Run two.
ghdl --elab-run $GHDL_FLAGS can_sim --stop-time=2ms --assert-level=error
echo "can_sim ran to 2 ms without errors"
endgroup

group "bml1 loose tutorial sources: analyse only"
for f in bml1/seg.vhd bml1/seg2.vhd; do
    ghdl -a $GHDL_FLAGS "$f"
    echo "ok: $f"
done
for f in bml1/top2.v bml1/top3.v; do
    yosys -q -p "read_verilog $f; synth_xilinx -top top"
    echo "ok: $f"
done
endgroup

echo "All checks passed."
