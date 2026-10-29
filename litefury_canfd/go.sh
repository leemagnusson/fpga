#!/bin/sh
# Build (and, unless CI is set, program over JTAG). Uses ci/vivado.sh so the
# same command works natively or inside the Docker image.
cd "$(dirname "$0")" && exec ../ci/vivado.sh -mode batch -source go.tcl
