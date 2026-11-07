#!/usr/bin/env bash
# Second unattended batch: analog impairments and patterned timing errors, one SQI measurement
# each (tools/sqi_sweep.py). Waits for the jitter sweep (arb/sqi_sweep.log) to finish first.
set -u
cd "$(dirname "$0")/.."
until grep -q "sweep done" arb/sqi_sweep.log 2>/dev/null; do sleep 60; done
python3 -I tools/sqi_sweep.py -o arb/sqi_experiments.csv \
  "amp0.8=-a 0.4" "amp0.5=-a 0.25" "amp0.44=-a 0.22" "amp0.4=-a 0.2" \
  "edge20=--edge 20e-9" "edge30=--edge 30e-9" "edge40=--edge 40e-9" \
  "lp8=--lowpass 8e-9" "lp15=--lowpass 15e-9" "lp25=--lowpass 25e-9" \
  "ring30M_20=--ring 30e6 0.2 20e-9" "ring30M_40=--ring 30e6 0.4 20e-9" "ring60M_30=--ring 60e6 0.3 15e-9" \
  "off50=--offset 0.05" "off100=--offset 0.1" "off150=--offset 0.15" \
  "noise5=--noise 0.005" "noise10=--noise 0.01" "noise15=--noise 0.015" \
  "tone1M_30=--tone 1e6 0.03" "tone1M_60=--tone 1e6 0.06" "tone100k_100=--tone 100e3 0.1" "tone5M_30=--tone 5e6 0.03" \
  "dcd4=--dcd 4e-9" "dcd8=--dcd 8e-9" "dcd12=--dcd 12e-9" \
  "pj100k_3=--pj 100e3 3e-9" "pj100k_6=--pj 100e3 6e-9" "pj1M_4=--pj 1e6 4e-9" "pj5M_4=--pj 5e6 4e-9" \
  "ddj4=--ddj 4e-9" "ddj8=--ddj 8e-9" \
  "uni2=--jitter 2e-9 --jitter-dist uniform" "uni3.5=--jitter 3.5e-9 --jitter-dist uniform" \
  "edge30_j2=--edge 30e-9 --jitter 2e-9" "amp0.6_j3=-a 0.3 --jitter 3e-9" "lp15_j2=--lowpass 15e-9 --jitter 2e-9" \
  "j2.5r=--jitter 2.5e-9"
