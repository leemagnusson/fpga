#!/bin/bash
# Capture one generator frame on the scope with a timebase long enough for the
# whole frame, then restore the user's timebase, and draw the eye diagram.
# usage: eye_capture.sh <waveform.csv> <out_prefix>   (writes out_prefix.f32/.hdr/.png)
set -u
cd "$(dirname "$0")/.."
WAV=$1; OUT=$2
M="python3 -I tools/mxo_arb.py"
RANGE=$($M scpi 'TIM:RANG?' | sed 's/.*-> //')
SRATE=$($M scpi 'ACQ:SRAT?' | sed 's/.*-> //')
echo "scope before: range $RANGE s, $SRATE Sa/s"
$M load "$WAV" | tail -1
$M scpi 'TIM:RANG 300e-6' >/dev/null          # 300 us, trigger at centre: 150 us after the trigger covers a 110 us frame
sleep 0.5
python3 -I tools/mxo_capture.py "$OUT.f32" | tail -1
$M scpi "TIM:RANG $RANGE" >/dev/null
echo "scope restored: range $($M scpi 'TIM:RANG?' | sed 's/.*-> //') s"
python3 -I tools/t1s_eye.py "$OUT.f32" -o "$OUT.png"
