#!/bin/sh
# Bring up the LiteFury CAN FD interface at 1 Mbit/s nominal / 8 Mbit/s data.
#
# The mainline ctucanfd_pci driver assumes the core runs at 100 MHz, but this
# card clocks it at 80 MHz so that 8 Mbit/s is an exact division (12.5 ns
# quanta; 100 MHz cannot hit 8 Mbit/s exactly). Therefore "bitrate 1000000"
# would be wrong here: give the bit timing explicitly in quanta instead.
#   The driver turns tq=10 ns into prescaler 1 (its 100 MHz belief), so one
#   quantum is really 12.5 ns:
#     nominal: 1 + 29 + 30 + 20 = 80 tq -> 1.000 Mbit/s, sample point 75 %
#     data:    1 +  3 +  3 +  3 = 10 tq -> 8.000 Mbit/s, sample point 70 %
# The early data sample point and the 3 tq jump width leave room for nodes
# that are slightly off 8 Mbit/s (see host/05-ctucanfd.network).
dev=${1:-can0}
set -e
ip link set "$dev" down 2>/dev/null || true
ip link set "$dev" type can \
    tq 10  prop-seg 29 phase-seg1 30 phase-seg2 20 sjw 20 \
    dtq 10 dprop-seg 3 dphase-seg1 3 dphase-seg2 3 dsjw 3 \
    fd on
ip link set "$dev" up
ip -details link show "$dev"
