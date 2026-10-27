#!/usr/bin/env bash
# Build the Docker image that ci/vivado.sh runs Vivado in.
#
#   ci/docker/build.sh          small image; Vivado is mounted from the host
#                               at run time          -> vivado-runtime:<ver>
#   ci/docker/build.sh --web INSTALLER.bin
#                               installs a minimal Vivado (Artix-7 only, about
#                               20 GB) from the AMD web installer during the
#                               build; no host Vivado needed -> vivado:<ver>
#                               Prompts once for your AMD account to create
#                               the download token (kept in ~/.Xilinx).
#
# VIVADO_HOME  host install root, e.g. /opt/Xilinx/2026.1 (the directory that
#              contains Vivado/, Vitis/, data/ ...). Auto-detected from the
#              `vivado` executable on PATH if unset. Not used by --web.
# DEVICES      device families for --web (default "Artix-7 FPGAs"; see
#              ci/vivado-install/install.sh --list-devices)
set -euo pipefail
self=$(readlink -f "$0")
cd "$(dirname "$self")"
repo_root=$(cd ../.. && pwd)

web=""
while [ $# -gt 0 ]; do
    case "$1" in
        --web) web=$2; shift 2 ;;
        -h|--help) sed -n '2,19p' "$self"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ -n "$web" ]; then
    [ -f "$web" ] || { echo "installer not found: $web" >&2; exit 1; }
    web=$(readlink -f "$web")
    version=$(basename "$web" | sed -E 's/.*Unified_(SDI_)?([0-9]{4}\.[0-9])_.*/\2/')
    xil_home=$(getent passwd "$(id -u)" | cut -d: -f6)/.Xilinx
    if [ ! -f "$xil_home/wi_authentication_key" ]; then
        # Creates the token on the host (interactive AMD login) and stops.
        "$repo_root/ci/vivado-install/install.sh" --installer "$web" --prepare-only
    fi
    echo "Building vivado:$version from $(basename "$web") (downloads ~20 GB from AMD)"
    DOCKER_BUILDKIT=1 docker build \
        --target web \
        --build-arg "VIVADO_VERSION=$version" \
        --build-arg "INSTALLER=$(basename "$web")" \
        --build-arg "DEVICES=${DEVICES:-Artix-7 FPGAs}" \
        --build-context "installer=$(dirname "$web")" \
        --secret "id=xilinx_auth,src=$xil_home/wi_authentication_key" \
        -f Dockerfile -t "vivado:$version" "$repo_root"
    echo
    echo "Done. Use it with:  VIVADO_DOCKER_IMAGE=vivado:$version VIVADO_HOME=none ci/vivado.sh ..."
    exit 0
fi

if [ -z "${VIVADO_HOME:-}" ]; then
    if ! command -v vivado >/dev/null; then
        echo "vivado is not on PATH; set VIVADO_HOME to the install root" >&2
        exit 1
    fi
    VIVADO_HOME=$(cd "$(dirname "$(readlink -f "$(command -v vivado)")")/../.." && pwd)
fi
version=$(basename "$VIVADO_HOME")
if [ ! -x "$VIVADO_HOME/Vivado/bin/vivado" ]; then
    echo "no Vivado/bin/vivado under $VIVADO_HOME" >&2
    exit 1
fi

echo "Building vivado-runtime:$version (Vivado mounted from $VIVADO_HOME at run time)"
DOCKER_BUILDKIT=1 docker build \
    --target runtime \
    -t "vivado-runtime:$version" .
echo
echo "Done. Use it with:  VIVADO_DOCKER_IMAGE=vivado-runtime:$version ci/vivado.sh ..."
