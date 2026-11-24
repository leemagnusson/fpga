#!/bin/sh
# One-time host setup for the CAN FD cards. Run as root:
#   sudo sw/host-setup.sh [<uuid of the Thunderbolt enclosure holding the card>]
# Installs
#   /etc/systemd/network/05-ctucanfd.network   correct bit timing for the cards' interfaces (systemd-networkd)
#   /etc/udev/rules.d/70-ctucanfd-flash.rules  BAR0 access for group plugdev (sw/flash.py without root),
#                                              and keeps the card's PCIe port awake across FPGA reloads
#   /usr/local/sbin/ctucanfd-relink (+ .service, /etc/default/ctucanfd-relink)
#                                              for a card in a Thunderbolt enclosure: brings it back on
#                                              the bus after an FPGA reload (flash.py reboot / update)
# and applies both to cards that are already plugged in.
set -e
here=$(cd "$(dirname "$0")" && pwd)
install -m 644 "$here/host/05-ctucanfd.network" /etc/systemd/network/
install -m 644 "$here/host/70-ctucanfd-flash.rules" /etc/udev/rules.d/
install -m 755 "$here/host/ctucanfd-relink" /usr/local/sbin/
install -m 644 "$here/host/ctucanfd-relink.service" /etc/systemd/system/
systemctl daemon-reload
udevadm control --reload
udevadm trigger --action=change --subsystem-match=pci --attr-match=vendor=0x1760
udevadm settle
networkctl reload
for n in /sys/class/net/*; do
    [ "$(basename "$(readlink -f "$n/device/driver" 2>/dev/null)")" = ctucanfd_pci ] || continue
    networkctl reconfigure "$(basename "$n")"
done
# Which Thunderbolt enclosure holds the card: ctucanfd-relink only ever touches the one named in
# its config. Take the only authorized device at the end of a Thunderbolt chain, if there is
# exactly one and a card is on the bus; otherwise leave it to be filled in by hand.
cfg=/etc/default/ctucanfd-relink
if [ ! -e "$cfg" ] || [ -n "${1:-}" ]; then
    uuid=; n=0
    for d in /sys/bus/thunderbolt/devices/*-*; do
        [ -e "$d/unique_id" ] || continue
        case $(basename "$d") in *-0) continue ;; esac              # the host's own router
        ls -d "$d"/*-* > /dev/null 2>&1 && continue                 # something is connected behind it: a dock
        [ "$(cat "$d/authorized")" = 1 ] || continue
        uuid=$(cat "$d/unique_id"); name=$(cat "$d/device_name" 2>/dev/null); n=$((n + 1))
    done
    grep -qs 0x1760 /sys/bus/pci/devices/*/vendor || n=0
    if [ -n "${1:-}" ]; then
        uuid=$1; n=1; name=
        for d in /sys/bus/thunderbolt/devices/*-*; do
            [ "$(cat "$d/unique_id" 2>/dev/null)" = "$uuid" ] && name=$(cat "$d/device_name" 2>/dev/null)
        done
        [ -n "$name" ] || { echo "host-setup.sh: no connected Thunderbolt device has the id $uuid (boltctl list)" >&2; exit 1; }
    fi
    {
        echo "# /etc/default/ctucanfd-relink"
        echo "# The Thunderbolt enclosure that holds the CAN FD card, by its unique id (boltctl list, \"uuid\")."
        echo "# ctucanfd-relink re-authorizes this enclosure when the card has dropped off the bus after an"
        echo "# FPGA reload; no other device is touched. Leave it empty if the card is not behind Thunderbolt."
        if [ "$n" = 1 ]; then echo "ENCLOSURE_UUID=$uuid   # $name"; else echo "ENCLOSURE_UUID="; fi
    } > "$cfg"
    if [ "$n" = 1 ]; then echo "$cfg: enclosure $name ($uuid)"
    else echo "$cfg: no single Thunderbolt enclosure with a card found; set ENCLOSURE_UUID there if the card is in one"; fi
fi
# A card whose FPGA reloaded before this was installed is still off the bus: fetch it.
if ! grep -qs 0x1760 /sys/bus/pci/devices/*/vendor; then
    systemctl start ctucanfd-relink.service || true
    journalctl -u ctucanfd-relink.service -n 3 --no-pager -o cat || true
    udevadm settle
fi
echo "installed; interfaces of the cards:"
for n in /sys/class/net/*; do
    [ "$(basename "$(readlink -f "$n/device/driver" 2>/dev/null)")" = ctucanfd_pci ] && ip -details link show "$(basename "$n")" | grep -E '^[0-9]+:|tq '
done
ls -l /sys/bus/pci/devices/*/resource0 2>/dev/null | grep plugdev || true
