#!/usr/bin/env bash
# Run both testbenches with GHDL. Locally without GHDL installed:
#   docker run --rm -v "$PWD/..":/src -w /src/t1s_trigger hdlc/ghdl:yosys sim/run.sh
# tb_oled leaves sim/oled_frame.ppm (python3 sim/ppm2png.py sim/oled_frame.ppm frame.png to view).
set -euo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
rtl="rtl/t1s_pkg.vhd rtl/dme_rx.vhd rtl/t1s_pcs_rx.vhd rtl/plca_track.vhd rtl/pulse_stretch.vhd \
     rtl/seg7.vhd rtl/t1s_monitor.vhd rtl/oled_font_pkg.vhd rtl/bcd_rate.vhd rtl/trig_screen.vhd \
     rtl/oled_ssd1331.vhd rtl/oled_status.vhd rtl/top.vhd"
# shellcheck disable=SC2086
ghdl -a --std=08 --workdir="$work" $rtl sim/tb_top.vhd sim/tb_oled.vhd
ghdl --elab-run --std=08 --workdir="$work" tb_top --ieee-asserts=disable-at-0 --assert-level=failure "$@"
ghdl --elab-run --std=08 --workdir="$work" tb_oled --ieee-asserts=disable-at-0 --assert-level=failure -gPPM_FILE=sim/oled_frame.ppm "$@"
