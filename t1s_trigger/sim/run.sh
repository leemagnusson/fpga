#!/usr/bin/env bash
# Run the testbench with GHDL. Locally without GHDL installed:
#   docker run --rm -v "$PWD/..":/src -w /src/t1s_trigger hdlc/ghdl:yosys sim/run.sh
set -euo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
ghdl -a --std=08 --workdir="$work" rtl/t1s_pkg.vhd rtl/dme_rx.vhd rtl/t1s_pcs_rx.vhd \
    rtl/plca_track.vhd rtl/pulse_stretch.vhd rtl/seg7.vhd rtl/t1s_monitor.vhd rtl/top.vhd \
    sim/tb_top.vhd
ghdl --elab-run --std=08 --workdir="$work" tb_top --ieee-asserts=disable-at-0 --assert-level=failure "$@"
