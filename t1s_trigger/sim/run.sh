#!/usr/bin/env bash
# Run both testbenches with GHDL. Locally without GHDL installed:
#   docker run --rm --user "$(id -u)" -v "$PWD/..":/src -w /src/t1s_trigger hdlc/ghdl:yosys sim/run.sh
# tb_oled leaves sim/oled_frame.ppm (python3 sim/ppm2png.py sim/oled_frame.ppm frame.png to view).
#
# Waveforms:  sim/run.sh --wave   writes sim/tb_top.ghw and sim/tb_oled.ghw (GTKWave)
#             sim/run.sh --vcd    writes sim/tb_top.vcd and sim/tb_oled.vcd (any viewer,
#                                 or sim/vcd2svg.py for a picture without one)
# Any other argument is passed to both GHDL runs (e.g. --stop-time=100us).
set -euo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d)
echo $work
trap 'rm -rf "$work"' EXIT
wave=""
args=()
for a in "$@"; do
    case $a in
        --wave) wave=ghw ;;
        --vcd)  wave=vcd ;;
        *)      args+=("$a") ;;
    esac
done
dump() {    # $1 = testbench name
    case $wave in
        ghw) echo "--wave=sim/$1.ghw" ;;
        vcd) echo "--vcd=sim/$1.vcd" ;;
    esac
}
rtl="rtl/t1s_pkg.vhd rtl/oversample_in.vhd rtl/edge_time.vhd rtl/sqi_calc.vhd rtl/clk_gen.vhd rtl/t1s_sqi.vhd rtl/dme_rx.vhd rtl/t1s_pcs_rx.vhd rtl/plca_track.vhd rtl/pulse_stretch.vhd \
     rtl/seg7.vhd rtl/t1s_monitor.vhd rtl/oled_font_pkg.vhd rtl/bcd_rate.vhd rtl/trig_screen.vhd \
     rtl/oled_ssd1331.vhd rtl/oled_status.vhd rtl/top.vhd"
# shellcheck disable=SC2086
ghdl -a --std=08 --workdir="$work" $rtl sim/tb_top.vhd sim/tb_oled.vhd sim/tb_sqi.vhd
ghdl --elab-run --std=08 --workdir="$work" tb_top --ieee-asserts=disable-at-0 --assert-level=failure \
     $(dump tb_top) "${args[@]}"
ghdl --elab-run --std=08 --workdir="$work" tb_sqi --ieee-asserts=disable-at-0 --assert-level=failure \
     $(dump tb_sqi) "${args[@]}"
ghdl --elab-run --std=08 --workdir="$work" tb_oled --ieee-asserts=disable-at-0 --assert-level=failure \
     -gPPM_FILE=sim/oled_frame.ppm $(dump tb_oled) "${args[@]}"
