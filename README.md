# fpga

Hobby FPGA projects, mostly targeting a Basys 3 board (Artix-7 `xc7a35tcpg236-1`).

| Directory    | What it is                                                     | Build                    |
|--------------|----------------------------------------------------------------|--------------------------|
| `bml1/ch4`   | LED shift register built from UNISIM primitives (VHDL + Verilog) | `cd bml1/ch4 && ./go.sh` |
| `bml1/ch5`   | Same design in behavioural RTL with a 1 Hz pulse               | `cd bml1/ch5 && ./go.sh` |
| `bml1/seg`, `bml1/seg2` | Seven-segment display, switches and buttons (`seg2` counts button presses per second) | `cd bml1/seg2 && ./go.sh` |
| `can_timing` | CAN message timing model and `can_sim` testbench (sim only)    | Vivado project `can_timing/project_1` |
| `litefury_canfd` | CAN FD PCIe card on a LiteFury, SocketCAN via the mainline driver | `cd litefury_canfd && ./go.sh` (see its README) |
| `t1s_trigger` | 10BASE-T1S bus monitor with switch-selected scope trigger outputs, plus the KiCad tap Pmod | `cd t1s_trigger && ./go.sh` (see its README) |
| `src`        | Early BCD counter experiments (not currently building)         |                          |

`go.sh` runs `go.tcl` in Vivado batch mode: synthesis, place, route, reports,
bitstream, then `program.tcl` to load the board over JTAG. Set the `CI`
environment variable to skip the programming step:

```sh
CI=1 ./go.sh
```

## Continuous integration

Two GitHub Actions workflows live in `.github/workflows/`.

### `ci.yml` (runs everywhere, no setup)

Runs on GitHub-hosted runners in the `hdlc/ghdl:yosys` container and executes
`ci/check.sh`, which:

- synthesises `bml1/ch4` and `bml1/ch5` for Artix-7 with GHDL + Yosys
  (both the VHDL and the Verilog top), catching syntax, elaboration and
  non-synthesisable-construct errors;
- runs the `can_timing` testbench in GHDL for 2 ms;
- analyses the loose tutorial files in `bml1/`.

`ci/unisim_stub.vhd` provides behavioural stand-ins for the UNISIM primitives
used by `bml1/ch4` so GHDL can build it. The same script runs locally with:

```sh
docker run --rm -v "$PWD":/src -w /src hdlc/ghdl:yosys ci/check.sh
```

### `vivado.yml` (real Vivado flow, needs a self-hosted runner)

Vivado cannot run on GitHub-hosted runners, so this workflow runs each
project's `go.tcl` on a self-hosted runner, checks that `top.bit` was produced
and that timing was met, and uploads the bitstream and reports as artifacts.
Pull requests from forks never run on the self-hosted runner.

All Vivado invocations go through `ci/vivado.sh`, which runs Vivado natively
or inside a Docker image depending on the environment. It works on a dev
machine too:

```sh
cd bml1/ch5
../../ci/vivado.sh -mode batch -source go.tcl                                           # native
VIVADO_DOCKER_IMAGE=vivado-runtime:2026.1 ../../ci/vivado.sh -mode batch -source go.tcl   # Docker
```

#### Setting up a runner machine

A fresh Linux machine with sudo is enough. Four steps:

1. **Download the Vivado web installer** on that machine into `~/Downloads`:
   the Linux "Self Extracting Web Installer" (about 400 MB, AMD login
   required) from
   https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools.html

2. **Get a runner registration token** from the repo on GitHub: Settings,
   Actions, Runners, "New self-hosted runner", then copy the value from the
   `./config.sh --token ...` line. It is a short-lived code for adding one
   runner, not a personal access token, and it expires after an hour, so
   fetch it right before step 3. With the `gh` CLI logged in:

   ```sh
   gh api -X POST repos/leemagnusson/fpga/actions/runners/registration-token --jq .token
   ```

3. **Run the bootstrap** on the machine:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/leemagnusson/fpga/main/ci/runner/bootstrap.sh \
     | bash -s -- --token <registration token>
   ```

   It installs Docker and a few tools, clones this repo to `~/fpga`, installs
   a minimal Vivado (Artix-7 only, about 20 GB) to `~/Xilinx` from the web
   installer, builds the small `vivado-runtime` Docker image, and registers
   and starts the runner service with the `vivado` label. Expect three
   prompts: the sudo password, your AMD account e-mail and password (used
   once to create the installer's download token), and sudo again for the
   runner service. The Vivado download is the slow part. At the end the
   installer prints the machine's host ID for the next step.

4. **Licence and switch on.** Vivado 2026.1 needs its free BASIC licence
   file even for Artix-7, and it is node-locked, so each machine needs its
   own. Generate one for the printed host ID at the AMD licensing site and
   save it on the runner as `~/.Xilinx/Xilinx.lic`. Then set the repository
   variable `VIVADO_RUNNER` to `true` on GitHub (Settings, Secrets and
   variables, Actions, Variables) and push a commit or run the "Vivado
   build" workflow manually.

If the machine already has Vivado on its PATH, the bootstrap skips the
install and uses it. `ci/runner/install.sh --help` and
`ci/vivado-install/install.sh --help` describe the individual pieces for
doing it by hand.

#### Installing Vivado from the web, scripted

`ci/vivado-install/install.sh` drives the AMD web installer in batch mode and
installs the smallest useful Vivado: the 2026.1 "Vivado Design Suite" edition
with only the Artix-7 family, no DocNav, no Model Composer, no shortcuts. The
only manual parts are downloading the web installer and typing your AMD
account once.

```sh
ci/vivado-install/install.sh --installer ~/Downloads/FPGAs_AdaptiveSoCs_Unified_SDI_2026.1_*_Lin64.bin
```

Options: `--dest` (default `~/Xilinx`), `--devices "Artix-7 FPGAs,Spartan-7 FPGAs"`
(see `--list-devices` for the names), `--cable-drivers` for machines that
program boards, `--prepare-only` to stop after writing the config. For a
runner that should keep Vivado inside Docker instead of on the host,
`ci/docker/build.sh --web <installer>` runs the same install during an
image build; the installer comes in as a build context and the AMD token
as a build secret, so neither is stored in the image.

#### Option A: Vivado in Docker (recommended)

The runner machine needs Docker, with the runner's user in the `docker`
group. Build the image once on the runner:

```sh
ci/docker/build.sh
```

This builds `vivado-runtime:<version>`, a small Ubuntu 24.04 image with
Vivado's runtime libraries and locale. Vivado itself stays on the host and is
bind-mounted read-only into the container at run time, so nothing licensed is
copied into an image and there is no AMD installer or auth token to deal
with. The install root is found from `vivado` on PATH, or set `VIVADO_HOME`.
Because the container is Ubuntu 24.04, the `libncurses.so.5` start-up failure
on newer host distributions does not occur.

Vivado 2026.1 needs its free BASIC license file even for WebPACK parts. The
wrapper mounts `~/.Xilinx/Xilinx.lic` into the container automatically, or
set `VIVADO_LICENSE_FILE` to point at it. The container uses the host network
so a node-locked license still matches the host ID.

Then put `VIVADO_DOCKER_IMAGE=vivado-runtime:2026.1` in the runner's `.env`
file (per machine), or set it as a repository variable (applies to every
runner and overrides `.env`).

#### Option B: Vivado natively on the runner

Make sure `vivado` is on the runner service's `PATH`, or set the repository
variable `VIVADO_SETTINGS` to the path of Vivado's `settings64.sh`.

Note for Ubuntu newer than 24.04: Vivado 2026.1 does not recognise the OS and
fails at start-up with `libncurses.so.5: cannot open shared object file`,
while still exiting 0. Point it at its own bundled copy, for example in the
runner's `.env` file:

```sh
LD_LIBRARY_PATH=<vivado-install>/Vivado/lib/lnx64.o/Ubuntu/24
```

On such an OS Vivado also spills part of `/etc/os-release` into the comment
banner of every HDL file it generates, which breaks synthesis of block
designs with `syntax error near 'VERSION_ID'`. `litefury_canfd/go.tcl`
repairs the generated files (see `litefury_canfd/fix_banners.tcl`); the
other projects generate no HDL and are unaffected.
