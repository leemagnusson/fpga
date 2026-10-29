#!/bin/sh
# Bring up the LiteFury CAN FD interface at 1 Mbit/s nominal / 8 Mbit/s data.
#
# The mainline ctucanfd_pci driver assumes the core runs at 100 MHz, but this
# card clocks it at 80 MHz so that 8 Mbit/s is an exact division (12.5 ns
# quanta; 100 MHz cannot hit 8 Mbit/s exactly). Therefore "bitrate 1000000"
# would be wrong here: give the bit timing explicitly in quanta instead.
#   The driver turns tq=10 ns into prescaler 1 (its 100 MHz belief), so one
#   quantum is really 12.5 ns:
#     nominal: 1 + 31 + 32 + 16 = 80 tq -> 1.000 Mbit/s, sample point 80 %
#     data:    1 +  3 +  4 +  2 = 10 tq -> 8.000 Mbit/s, sample point 80 %
dev=${1:-can0}
set -e
ip link set "$dev" down 2>/dev/null || true
ip link set "$dev" type can \
    tq 10  prop-seg 31 phase-seg1 32 phase-seg2 16 sjw 16 \
    dtq 10 dprop-seg 3 dphase-seg1 4 dphase-seg2 2 dsjw 2 \
    fd on
ip link set "$dev" up
ip -details link show "$dev"
