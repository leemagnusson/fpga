#!/bin/sh
# Replace the in-tree ctucanfd modules with the hardware-timestamp build from
# ./driver (compile it first on the host:
#   make -C /lib/modules/$(uname -r)/build M=$PWD/driver modules ).
# Run as root. Pass the directory holding the .ko files (default ./driver).
d=${1:-$(dirname "$0")/driver}
set -e
ip link set can0 down 2>/dev/null || true
rmmod ctucanfd_pci 2>/dev/null || true
rmmod ctucanfd 2>/dev/null || true
modprobe can_dev
insmod "$d/ctucanfd.ko"
insmod "$d/ctucanfd_pci.ko"
dmesg | grep -i "ctucanfd\|timestamp" | tail -5
ethtool -T can0
