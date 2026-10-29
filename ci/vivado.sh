#!/usr/bin/env bash
# Single entry point for running Vivado, natively or in Docker. Used by
# .github/workflows/vivado.yml and handy on a dev machine:
#
#   cd bml1/ch5 && ../../ci/vivado.sh -mode batch -source go.tcl
#
# Environment:
#   VIVADO_DOCKER_IMAGE  run inside this image (built by ci/docker/build.sh),
#                        e.g. vivado-runtime:2026.1 or vivado:2026.1.
#                        Unset: run `vivado` from the host.
#   VIVADO_HOME          host install root to mount into the container. Auto-
#                        detected from `vivado` on PATH. Set to "none" to use
#                        the Vivado inside a self-contained image (build.sh --web) instead.
#   VIVADO_LICENSE_FILE  license file to make visible in the container.
#                        Defaults to ~/.Xilinx/Xilinx.lic if that exists.
#                        (Vivado 2026.1 needs its free BASIC license file even
#                        for WebPACK devices.)
#   VIVADO_SETTINGS      (native only) settings64.sh to source first, for
#                        runners where vivado is not on PATH.
#
# The current directory must be inside the repository; it is mounted into the
# container at the same path so go.tcl's relative paths keep working, and the
# container runs as your uid so output files are owned by you.
set -euo pipefail

if [ -z "${VIVADO_DOCKER_IMAGE:-}" ]; then
    if [ -n "${VIVADO_SETTINGS:-}" ]; then
        # shellcheck disable=SC1090
        source "$VIVADO_SETTINGS"
    fi
    # Vivado 2026.1 only recognises Ubuntu 22/24 and otherwise fails at start-up
    # with "libncurses.so.5: cannot open shared object file" (while exiting 0).
    # On newer distributions point it at its own bundled copy.
    if command -v vivado >/dev/null && ! ldconfig -p 2>/dev/null | grep -q 'libncurses\.so\.5'; then
        root=$(cd "$(dirname "$(readlink -f "$(command -v vivado)")")/../.." && pwd)
        for d in "$root/Vivado/lib/lnx64.o/Ubuntu/24" "$root/Vivado/lib/lnx64.o/Ubuntu/22"; do
            if [ -e "$d/libncurses.so.5" ]; then
                export LD_LIBRARY_PATH="$d${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
                break
            fi
        done
    fi
    exec vivado "$@"
fi

repo=$(cd "$(dirname "$0")/.." && pwd)
case "$PWD/" in
    "$repo"/*) ;;
    *) echo "ci/vivado.sh: run it from inside $repo" >&2; exit 2 ;;
esac

docker_args=(
    run --rm
    --user "$(id -u):$(id -g)"
    # Host network so a node-locked license sees the host's MAC address.
    --network host
    -e HOME=/tmp
    -e CI="${CI:-true}"
    -v "$repo:$repo"
    -w "$PWD"
)

license=${VIVADO_LICENSE_FILE:-$HOME/.Xilinx/Xilinx.lic}
if [ -f "$license" ]; then
    # mounted outside ~/.Xilinx so Vivado can still create its own (writable) ~/.Xilinx
    docker_args+=(
        -v "$license:/tmp/xilinx-license/Xilinx.lic:ro"
        -e XILINXD_LICENSE_FILE=/tmp/xilinx-license/Xilinx.lic
    )
fi

if [ "${VIVADO_HOME:-}" != "none" ]; then
    if [ -z "${VIVADO_HOME:-}" ] && command -v vivado >/dev/null; then
        VIVADO_HOME=$(cd "$(dirname "$(readlink -f "$(command -v vivado)")")/../.." && pwd)
    fi
    if [ -n "${VIVADO_HOME:-}" ]; then
        docker_args+=(
            -v "$VIVADO_HOME:$VIVADO_HOME:ro"
            -e "PATH=$VIVADO_HOME/Vivado/bin:/usr/local/bin:/usr/bin:/bin"
        )
    fi
fi

exec docker "${docker_args[@]}" "$VIVADO_DOCKER_IMAGE" vivado "$@"
