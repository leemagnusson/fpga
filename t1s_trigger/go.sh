#!/bin/sh
# Build and, unless CI is set, program the board. Goes through ci/vivado.sh so
# it works natively or in the Docker image.
cd "$(dirname "$0")" && exec ../ci/vivado.sh -mode batch -source go.tcl
