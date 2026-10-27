#!/usr/bin/env bash
# Set up this machine as a self-hosted Vivado runner for the repo, from
# scratch: no Docker or Vivado needed beforehand, only sudo and the AMD web
# installer in ~/Downloads. Run it straight from GitHub:
#
#   curl -fsSL https://raw.githubusercontent.com/leemagnusson/fpga/main/ci/runner/bootstrap.sh \
#     | bash -s -- --token <registration token>
#
# What it does:
#   1. installs git/curl/jq/zstd and Docker (get.docker.com) if missing
#   2. clones the repo to ~/fpga (or updates it)
#   3. Vivado: if `vivado` is already on PATH, uses it. Otherwise installs a
#      minimal Vivado (Artix-7 only) to ~/Xilinx from the newest
#      FPGAs_AdaptiveSoCs_Unified_*_Lin64.bin in ~/Downloads with
#      ci/vivado-install/install.sh (asks for your AMD account once)
#   4. builds the small vivado-runtime Docker image that mounts that install
#   5. runs ci/runner/install.sh to register and start the runner service
#
# Options:
#   --token TOKEN       runner registration token (see README, "the token")
#   --installer FILE    the web installer .bin, if not in ~/Downloads
#   --devices LIST      device families to install (default "Artix-7 FPGAs")
#   --repo URL          git URL to clone (default: this repo on GitHub)
#   --dir DIR           where to clone (default: ~/fpga)
#
# Afterwards: put a Vivado licence for this machine at ~/.Xilinx/Xilinx.lic
# and set the repository variable VIVADO_RUNNER=true on GitHub.

# Everything is inside main() so bash reads the whole script before running
# any of it; that keeps `curl | bash` safe when commands below use stdin.
main() {
    set -euo pipefail

    local token="" installer="" devices="Artix-7 FPGAs" dir="$HOME/fpga"
    local repo="https://github.com/leemagnusson/fpga.git"
    while [ $# -gt 0 ]; do
        case "$1" in
            --token) token=$2; shift 2 ;;
            --installer) installer=$2; shift 2 ;;
            --devices) devices=$2; shift 2 ;;
            --repo) repo=$2; shift 2 ;;
            --dir) dir=$2; shift 2 ;;
            -h|--help) sed -n '2,27p' "$0" 2>/dev/null || echo "see the header of ci/runner/bootstrap.sh"; return 0 ;;
            *) echo "unknown option: $1" >&2; return 2 ;;
        esac
    done
    [ -n "$token" ] || { echo "need --token (GitHub: Settings -> Actions -> Runners -> New self-hosted runner)" >&2; return 2; }

    # Check the installer early so a missing download is caught before sudo.
    if ! command -v vivado >/dev/null; then
        if [ -z "$installer" ]; then
            installer=$(ls -t "$HOME"/Downloads/FPGAs_AdaptiveSoCs_Unified_*Lin64.bin 2>/dev/null | head -1 || true)
        fi
        [ -f "${installer:-}" ] || {
            echo "Vivado is not installed and no web installer was found in ~/Downloads." >&2
            echo "Download the Linux 'Self Extracting Web Installer' (AMD login required) from" >&2
            echo "  https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools.html" >&2
            echo "into ~/Downloads, or pass --installer FILE, then rerun." >&2
            return 1
        }
    fi

    echo "== 1/5 prerequisites"
    if command -v apt-get >/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq git curl jq zstd </dev/null
    elif command -v dnf >/dev/null; then
        sudo dnf install -y -q git curl jq zstd </dev/null
    else
        echo "unsupported distro: install git curl jq zstd and Docker by hand, then rerun" >&2; return 1
    fi
    if ! command -v docker >/dev/null; then
        curl -fsSL https://get.docker.com | sudo sh
    fi
    sudo usermod -aG docker "$USER"
    sudo systemctl enable --now docker

    echo "== 2/5 repo -> $dir"
    if [ -d "$dir/.git" ]; then
        git -C "$dir" pull --ff-only </dev/null
    else
        git clone "$repo" "$dir" </dev/null
    fi
    cd "$dir"

    echo "== 3/5 Vivado"
    if command -v vivado >/dev/null; then
        echo "using the Vivado already on PATH: $(command -v vivado)"
    else
        echo "installing from $installer (AMD login follows; the download takes a while)"
        ci/vivado-install/install.sh --installer "$installer" --devices "$devices" </dev/tty
        local ver
        ver=$(basename "$installer" | sed -E 's/.*Unified_(SDI_)?([0-9]{4}\.[0-9])_.*/\2/')
        export PATH="$HOME/Xilinx/$ver/Vivado/bin:$PATH"
        grep -q "Xilinx/$ver/Vivado/bin" "$HOME/.profile" 2>/dev/null \
            || echo "export PATH=\"\$HOME/Xilinx/$ver/Vivado/bin:\$PATH\"" >> "$HOME/.profile"
    fi

    echo "== 4/5 Docker image"
    # Group membership is not active in this shell yet; sg runs with it.
    sg docker -c "ci/docker/build.sh" </dev/null
    local image
    image="vivado-runtime:$(basename "$(cd "$(dirname "$(readlink -f "$(command -v vivado)")")/../.." && pwd)")"

    echo "== 5/5 runner"
    sg docker -c "ci/runner/install.sh --token '$token' --image '$image'" </dev/tty

    cat <<MSG

Done. Two things remain:
  * Vivado licence: generate a free BASIC licence for THIS machine's host ID
    (printed above by the installer) at https://www.xilinx.com/getlicense and
    save it as ~/.Xilinx/Xilinx.lic. Vivado will not start without it.
  * On GitHub, set the repository variable VIVADO_RUNNER = true.
MSG
}

main "$@"
