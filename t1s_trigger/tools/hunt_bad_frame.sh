#!/usr/bin/env bash
# Capture single shots on the scope until the host adapter (t1s0) flags one as errored.
# usage: hunt_bad_frame.sh <prefix> [max_shots] [wanted]
set -u
cd "$(dirname "$0")/.."
prefix=$1; max=${2:-40}; wanted=${3:-2}
found=0
dropped() { ip -s link show t1s0 | sed -n 4p | awk '{print $4}'; }
for i in $(seq 1 "$max"); do
  d0=$(dropped)
  python3 -I tools/mxo_capture.py "${prefix}_try.f32" > /dev/null || { python3 -I tools/mxo_arb.py clear > /dev/null; continue; }
  sleep 0.3
  d1=$(dropped)
  if [ "$d1" != "$d0" ]; then
    found=$((found + 1))
    mv "${prefix}_try.f32" "${prefix}_bad${found}.f32"; mv "${prefix}_try.f32.hdr" "${prefix}_bad${found}.f32.hdr"
    echo "shot $i: host dropped $d0 -> $d1, saved ${prefix}_bad${found}.f32"
    [ "$found" -ge "$wanted" ] && break
  else
    echo "shot $i: good"
  fi
done
rm -f "${prefix}_try.f32" "${prefix}_try.f32.hdr"
echo "hunt done: $found bad frames"
