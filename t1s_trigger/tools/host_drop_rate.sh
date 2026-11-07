#!/usr/bin/env bash
# Load a waveform, fire N shots, report how many the host adapter (t1s0) flagged and
# how many symbol errors the motor counted.  usage: host_drop_rate.sh file.csv [shots]
set -u
cd "$(dirname "$0")/.."
f=$1; n=${2:-800}
python3 -I tools/mxo_arb.py load "$f" > /dev/null || { echo "load failed: $f"; exit 1; }
h0=$(ip -s link show t1s0 | sed -n 4p | awk '{print $2, $4}')
m0=$(motor_util -e --set-api phy_stats | grep -E 'RXSE' | awk '{print $2}'); m0=${m0:-0}
python3 -I tools/mxo_arb.py fire -n "$n" --gap 0.02 > /dev/null
sleep 0.5
h1=$(ip -s link show t1s0 | sed -n 4p | awk '{print $2, $4}')
m1=$(motor_util -e --set-api phy_stats | grep -E 'RXSE' | awk '{print $2}'); m1=${m1:-0}
read p0 d0 <<< "$h0"; read p1 d1 <<< "$h1"
printf '%-40s shots %d  host good %d flagged %d (%.1f %%)  motor symbol errors %d\n' \
  "$(basename "$f")" "$n" $((p1 - p0)) $((d1 - d0)) "$(echo "100*($d1-$d0)/$n" | bc -l)" $((m1 - m0))
