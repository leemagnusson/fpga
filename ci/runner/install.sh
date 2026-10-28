#!/usr/bin/env bash
# Install this repo's GitHub Actions self-hosted runner on this machine, as a
# systemd service with the "vivado" label, preconfigured to run Vivado through
# ci/vivado.sh (in Docker by default).
#
#   ci/runner/install.sh --token <registration token> [options]
#
# Get a registration token (valid for one hour) from the repo on GitHub:
# Settings -> Actions -> Runners -> "New self-hosted runner", or with gh:
#   gh api -X POST repos/<owner>/<repo>/actions/runners/registration-token --jq .token
#
# Options:
#   --token TOKEN     registration token (or set RUNNER_TOKEN)
#   --image IMAGE     Docker image for Vivado. Default: vivado:<ver> if that
#                     image exists locally, else vivado-runtime:<ver>. Use
#                     "none" to run Vivado natively from PATH instead.
#   --dir DIR         where to install the runner (default: ~/actions-runner-fpga,
#                     separate from any runner already serving another repo)
#   --name NAME       runner name (default: hostname)
#   --download-only   fetch and unpack the runner software, do not register
#
# Afterwards set the repository variable VIVADO_RUNNER to "true" to turn the
# Vivado workflow on.
set -euo pipefail

token=${RUNNER_TOKEN:-}
image=""
dir="$HOME/actions-runner-fpga"
name=$(hostname)
download_only=0
while [ $# -gt 0 ]; do
    case "$1" in
        --token) token=$2; shift 2 ;;
        --image) image=$2; shift 2 ;;
        --dir) dir=$2; shift 2 ;;
        --name) name=$2; shift 2 ;;
        --download-only) download_only=1; shift ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

repo_root=$(cd "$(dirname "$0")/../.." && pwd)
remote=$(git -C "$repo_root" remote get-url origin)
# git@github.com:owner/repo.git  or  https://github.com/owner/repo(.git)
slug=$(echo "$remote" | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')
url="https://github.com/$slug"

vivado_root=""
if command -v vivado >/dev/null; then
    vivado_root=$(cd "$(dirname "$(readlink -f "$(command -v vivado)")")/../.." && pwd)
fi

# --- Decide how Vivado will run --------------------------------------------
env_lines=()
if [ "$image" = "none" ]; then
    if [ -z "$vivado_root" ]; then
        echo "--image none, but vivado is not on PATH" >&2; exit 1
    fi
    echo "Vivado: native, $vivado_root"
else
    if ! docker info >/dev/null 2>&1; then
        echo "docker is not usable by $USER (install Docker and add $USER to the docker group)" >&2
        exit 1
    fi
    if [ -z "$image" ]; then
        ver=${vivado_root:+$(basename "$vivado_root")}
        if [ -n "$ver" ] && docker image inspect "vivado:$ver" >/dev/null 2>&1; then
            image="vivado:$ver"
        elif [ -n "$ver" ] && docker image inspect "vivado-runtime:$ver" >/dev/null 2>&1; then
            image="vivado-runtime:$ver"
        else
            image=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -m1 '^vivado' || true)
        fi
        if [ -z "$image" ]; then
            echo "no vivado image found; build one with ci/docker/build.sh or load an exported one" >&2
            exit 1
        fi
    fi
    docker image inspect "$image" >/dev/null 2>&1 || { echo "image $image not found" >&2; exit 1; }
    env_lines+=("VIVADO_DOCKER_IMAGE=$image")
    if docker run --rm --entrypoint sh "$image" -c 'command -v vivado' >/dev/null 2>&1; then
        echo "Vivado: Docker, $image (self-contained)"
        env_lines+=("VIVADO_HOME=none")
    elif [ -n "$vivado_root" ]; then
        echo "Vivado: Docker, $image with $vivado_root mounted"
        env_lines+=("VIVADO_HOME=$vivado_root")
    else
        echo "$image does not contain Vivado and vivado is not on PATH" >&2; exit 1
    fi
fi
if [ ! -f "$HOME/.Xilinx/Xilinx.lic" ]; then
    echo "WARNING: no $HOME/.Xilinx/Xilinx.lic. Vivado 2026.1 needs its free BASIC licence"
    echo "         (node-locked to this machine) even for WebPACK parts. Generate one at"
    echo "         https://www.xilinx.com/getlicense and put it there."
fi

# --- Download the runner ----------------------------------------------------
mkdir -p "$dir"
cd "$dir"
if [ ! -x ./config.sh ]; then
    tarball=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
        | jq -r '.assets[] | select(.name | test("^actions-runner-linux-x64-[0-9.]+\\.tar\\.gz$")) | .browser_download_url')
    echo "Downloading $(basename "$tarball") ..."
    curl -fL -sS -o runner.tar.gz "$tarball"
    tar xzf runner.tar.gz && rm runner.tar.gz
fi
printf '%s\n' "${env_lines[@]}" > .env
echo "Runner unpacked in $dir; .env contains:"
sed 's/^/    /' .env
if [ "$download_only" = 1 ]; then
    exit 0
fi

# --- Register and start as a service ---------------------------------------
if [ -z "$token" ]; then
    echo "need --token (see --help for how to get one)" >&2; exit 2
fi
if [ ! -f .runner ]; then
    echo "Installing runner dependencies (sudo) ..."
    sudo ./bin/installdependencies.sh
    ./config.sh --unattended --url "$url" --token "$token" --name "$name" --labels vivado --replace
fi
sudo ./svc.sh install "$USER"
sudo ./svc.sh start

cat <<MSG

Runner "$name" is registered for $url with label "vivado" and running as a service.
Finally, in the repo on GitHub set the Actions repository variable
    VIVADO_RUNNER = true
and push a commit (or run the "Vivado build" workflow manually).
MSG
