#!/usr/bin/env bash
# Scripted, minimal Vivado install from the AMD web installer: the
# "Vivado Design Suite" edition with only the device families you need
# (default: Artix-7, which covers the Basys 3), no DocNav, no Model Composer,
# no shortcuts. Everything is batch mode except the one AMD login.
#
#   ci/vivado-install/install.sh --installer ~/Downloads/FPGAs_AdaptiveSoCs_Unified_SDI_2026.1_*_Lin64.bin
#
# Before running it, download the Linux "Self Extracting Web Installer" (about
# 400 MB; AMD requires signing in) from
#   https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools.html
#
# Options:
#   --installer FILE   the web installer .bin (default: newest one in ~/Downloads)
#   --dest DIR         install root (default: ~/Xilinx). Vivado lands in DIR/<version>/Vivado
#   --devices LIST     comma-separated device families, exactly as the installer
#                      names them (default: "Artix-7 FPGAs"). Run with
#                      --list-devices to see the names for this installer.
#   --list-devices     print the module names the installer knows and exit
#   --prepare-only     extract, authenticate and write the config, but do not install
#   --no-libs          skip `sudo installLibs.sh` (installs OS packages Vivado needs)
#   --cable-drivers    also install the JTAG cable udev rules (sudo); only for
#                      machines that program boards
#
# Steps:
#   1. extract the web installer to a temp dir
#   2. authentication token: `xsetup -b AuthTokenGen` asks for your AMD
#      account e-mail and password once and stores a token in ~/.Xilinx
#      (reused on later runs; valid for a limited time)
#   3. `xsetup -b ConfigGen` writes this version's config template, which is
#      then edited: everything off except --devices
#   4. `xsetup --batch Install` downloads and installs (15-25 GB, takes a while)
#   5. installLibs.sh for OS packages
# Afterwards you still need a licence file: see the message at the end.
set -euo pipefail

installer=""
dest="$HOME/Xilinx"
devices="Artix-7 FPGAs"
prepare_only=0
list_devices=0
install_libs=1
cable_drivers=0
while [ $# -gt 0 ]; do
    case "$1" in
        --installer) installer=$2; shift 2 ;;
        --dest) dest=$2; shift 2 ;;
        --devices) devices=$2; shift 2 ;;
        --list-devices) list_devices=1; shift ;;
        --prepare-only) prepare_only=1; shift ;;
        --no-libs) install_libs=0; shift ;;
        --cable-drivers) cable_drivers=1; shift ;;
        -h|--help) sed -n '2,36p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$installer" ]; then
    installer=$(ls -t "$HOME"/Downloads/FPGAs_AdaptiveSoCs_Unified_*Lin64.bin 2>/dev/null | head -1 || true)
    [ -n "$installer" ] || { echo "no installer found in ~/Downloads; pass --installer FILE" >&2; exit 1; }
fi
[ -f "$installer" ] || { echo "installer not found: $installer" >&2; exit 1; }
version=$(basename "$installer" | sed -E 's/.*Unified_(SDI_)?([0-9]{4}\.[0-9])_.*/\2/')
echo "Installer: $installer (version $version)"

work=$(mktemp -d "${TMPDIR:-/tmp}/xinstall.XXXXXX")
trap 'rm -rf "$work"' EXIT
echo "== extracting to $work"
# Run through sh so it also works from a read-only mount (Docker build).
sh "$installer" --noexec --keep --nox11 --target "$work/x" >/dev/null
xsetup="$work/x/xsetup"

# xsetup ignores $HOME and uses the passwd entry; this is where it writes.
xil_home=$(getent passwd "$(id -u)" | cut -d: -f6)/.Xilinx
mkdir -p "$xil_home"

echo "== config template (xsetup -b ConfigGen)"
rm -f "$xil_home/install_config.txt"
# Answers the "Select a Product" prompt with 2 (Vivado); an extra line in case
# the installer also asks for an edition.
printf '2\n1\n' | "$xsetup" -b ConfigGen >"$work/configgen.log" 2>&1 \
    || { cat "$work/configgen.log"; exit 1; }
cfg="$work/install_config.txt"
mv "$xil_home/install_config.txt" "$cfg"

if [ "$list_devices" = 1 ]; then
    sed -n 's/^Modules=//p' "$cfg" | tr ',' '\n' | sed 's/:[01]$//' | sort
    exit 0
fi

# Edit: destination, no shortcuts, every module off, then the chosen ones on.
sed -i -E \
    -e "s#^Destination=.*#Destination=$dest#" \
    -e 's/^CreateProgramGroupShortcuts=.*/CreateProgramGroupShortcuts=0/' \
    -e 's/^CreateDesktopShortcuts=.*/CreateDesktopShortcuts=0/' \
    -e 's/^CreateFileAssociation=.*/CreateFileAssociation=0/' \
    -e '/^Modules=/ s/:1(,|$)/:0\1/g' \
    "$cfg"
IFS=',' read -ra devlist <<<"$devices"
for dev in "${devlist[@]}"; do
    dev=$(echo "$dev" | sed -E 's/^ +| +$//g')
    if ! grep -q "^Modules=.*\(^\|,\)$dev:0" "$cfg" && ! grep -q "^Modules=\(.*,\)\?$dev:0" "$cfg"; then
        echo "device family '$dev' is not in this installer's module list (see --list-devices)" >&2
        exit 1
    fi
    sed -i "/^Modules=/ s/\(^Modules=\|,\)$dev:0/\1$dev:1/" "$cfg"
done
echo "Selected modules:"
sed -n 's/^Modules=//p' "$cfg" | tr ',' '\n' | grep ':1$' | sed 's/^/    /'
cp "$cfg" "$xil_home/install_config_$version.txt"
echo "Config saved as $xil_home/install_config_$version.txt"

echo "== AMD account authentication"
if [ -f "$xil_home/wi_authentication_key" ]; then
    echo "using existing token $xil_home/wi_authentication_key (delete it if downloads fail with an auth error)"
else
    echo "Enter your AMD account e-mail and password (used once to create a download token):"
    "$xsetup" -b AuthTokenGen </dev/tty
fi

if [ "$prepare_only" = 1 ]; then
    echo "prepare-only: stopping before installation. Config: $xil_home/install_config_$version.txt"
    exit 0
fi

echo "== installing to $dest (downloading from AMD; this takes a while)"
"$xsetup" --agree XilinxEULA,3rdPartyEULA --batch Install --config "$cfg"
vivado_dir="$dest/$version/Vivado"
[ -x "$vivado_dir/bin/vivado" ] || { echo "install finished but $vivado_dir/bin/vivado is missing" >&2; exit 1; }

if [ "$install_libs" = 1 ] && [ -x "$vivado_dir/scripts/installLibs.sh" ]; then
    echo "== OS packages (sudo installLibs.sh)"
    sudo "$vivado_dir/scripts/installLibs.sh" </dev/tty || echo "installLibs.sh failed; install the packages it lists by hand"
fi
if [ "$cable_drivers" = 1 ]; then
    echo "== cable drivers (sudo)"
    (cd "$vivado_dir/data/xicom/cable_drivers/lin64/install_script/install_drivers" && sudo ./install_drivers) </dev/tty
fi

hostid=$(ip -o link | awk '$2 !~ /^(lo|docker|veth|br-)/ {gsub(":", "", $17); print $17; exit}')
cat <<MSG

Vivado $version installed: $vivado_dir
Add it to PATH:    export PATH=$vivado_dir/bin:\$PATH
                   (or put that line in the runner's .env as PATH=...)

Licence: Vivado $version needs a licence file even for Artix-7. Generate the
free one at https://www.xilinx.com/getlicense for this machine's host ID
(MAC address) $hostid and save it as $xil_home/Xilinx.lic
MSG
