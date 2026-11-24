#!/bin/sh
# Install the ctucanfd driver copy from sw/driver with DKMS, so that it replaces
# the kernel's own modules now and is rebuilt for every new kernel. Run as root:
#   sudo sw/driver-install.sh            install (or update) and load it
#   sudo sw/driver-install.sh --remove   back to the kernel's own driver
#
# The copy is the mainline driver of Linux 7.0 with the changes described in
# ../README.md. If a later kernel changes the interfaces it uses, the DKMS build
# for that kernel fails and the kernel's own driver is used again: check with
#   dkms status ctucanfd-fpga2;  modinfo -F version ctucanfd
# (hwts-load.sh still loads freshly built modules by hand, for trying a change.)
set -e
here=$(cd "$(dirname "$0")" && pwd)
name=ctucanfd-fpga2
ver=$(sed -n 's/^#define CTUCANFD_FPGA2_VERSION "\(.*\)"$/\1/p' "$here/driver/ctucanfd.h")
[ -n "$ver" ] || { echo "driver-install.sh: no CTUCANFD_FPGA2_VERSION in driver/ctucanfd.h" >&2; exit 1; }

reload() {
    for n in /sys/class/net/*; do
        [ "$(basename "$(readlink -f "$n/device/driver" 2>/dev/null)")" = ctucanfd_pci ] && ip link set "$(basename "$n")" down
    done
    rmmod ctucanfd_pci 2>/dev/null || true
    rmmod ctucanfd 2>/dev/null || true
    modprobe ctucanfd_pci
}

# any version of the package installed earlier
for d in /var/lib/dkms/$name/*/; do
    [ -d "$d" ] || continue
    case $(basename "$d") in kernel-*) continue ;; esac
    dkms remove "$name/$(basename "$d")" --all || true
done
for d in /usr/src/$name-*/; do
    [ -f "$d/dkms.conf" ] && rm -rf "/usr/src/$(basename "$d")"
done
if [ "${1:-}" = --remove ]; then
    depmod -a
    reload
    echo "removed; loaded now: ctucanfd $(cat /sys/module/ctucanfd/version 2>/dev/null || echo '(kernel version)')"
    exit 0
fi

src=/usr/src/$name-$ver
mkdir "$src"
cp "$here"/driver/Makefile "$here"/driver/*.c "$here"/driver/*.h "$src/"
sed "s/@VERSION@/$ver/" "$here/driver/dkms.conf" > "$src/dkms.conf"
dkms add "$name/$ver"
dkms build "$name/$ver"
dkms install "$name/$ver"
reload
echo "installed $name $ver; loaded now: ctucanfd $(cat /sys/module/ctucanfd/version 2>/dev/null || echo '(no version: still the kernel driver?)') from $(modinfo -n ctucanfd)"
