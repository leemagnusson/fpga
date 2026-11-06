# LiteFury CAN FD card

A minimal CAN FD interface on the LiteFury (Artix-7 XC7A100T M.2 board) that
shows up in Linux as a normal SocketCAN device, driven by the mainline
`ctucanfd_pci` driver. No custom kernel module.

```
host <-- PCIe x4 Gen1 --> AXI PCIe bridge --> BAR0: board registers (ID, irq enable)
                                          --> BAR1: CTU CAN FD core (APB) --> J5/H5 --> CAN FD transceiver
```

- CAN controller: [CTU CAN FD](https://github.com/Logic-Design-Services/CTU-CAN-FD),
  ISO 11898-1:2015, up to 8 Mbit/s data phase; git submodule in
  `third_party/CTU-CAN-FD`.
- Core clock 80 MHz, so 1 Mbit/s and 8 Mbit/s are exact integer divisions.
- Interrupts via MSI (legacy INTx fallback).
- PCIe x4 at Gen1 (2.5 GT/s) by default; `PCIE_GEN=2` builds Gen2. The
  bridge's AXI clock is 125 MHz either way. Timing on the -2L speed grade is
  tight in the bridge's unused AXI-to-PCIe slave path: Gen1 closes with
  0.07 ns of slack at the default 128-bit AXI width (0.3 ns with
  `AXI_DATA_WIDTH=64`), Gen2 with 0.07 ns now that narrow-burst support on
  that unused port is off. A CAN card gains nothing from Gen2: CAN FD tops
  out at 8 Mbit/s and register accesses are latency-bound, where Gen2 saves
  well under 100 ns per read.

## Hardware

The LiteFury has no CAN transceiver. Connect a 3.3 V CAN FD transceiver
(e.g. TI TCAN1042HV, Microchip MCP2558FD, NXP TJA1462; it must be an FD-rated
part for 8 Mbit/s) to the board's I/O connector, bank 35, 3.3 V logic:

| Signal        | FPGA pin | Connector name | Transceiver |
|---------------|----------|----------------|-------------|
| `can_tx`      | J5       | AIO1_P         | TXD         |
| `can_rx`      | H5       | AIO1_N         | RXD         |
| `can_stby`    | K2       | AIO2_P         | STB / S (driven low = normal mode) |
| 3.3 V, GND    |          | on the same connector | VCC, GND |

Keep the TXD/RXD wires short (a few cm) for 8 Mbit/s, and terminate the bus
with 120 ohm at both ends. The pin names come from RHS Research's uEVB
schematic and were resolved to package pins with Vivado; verify against your
board revision before soldering.

LEDs (default view): LED1 = PCIe link up, LED2 = CAN interrupt activity,
LED3 = heartbeat, LED4 = interrupts enabled by the driver.

## Build

Needs Vivado (the design uses the AXI Memory Mapped to PCIe IP) and the CAN
core submodule:

```sh
git submodule update --init
cd litefury_canfd
./go.sh                 # ../ci/vivado.sh -mode batch -source go.tcl
```

Produces `top.bit`, `top.bin` and `reports/`. Without `CI` set it also loads
the bitstream over JTAG at the end. For PCIe the card has to be configured
before the host enumerates the bus, so for real use write the flash and
power-cycle the host:

```sh
../ci/vivado.sh -mode batch -source program_flash.tcl     # FLASH_PART=... for the 128 Mbit variant
```

Environment: `CTU_CAN_FD_SRC` (core location if not the submodule),
`PCI_VENDOR_ID` / `PCI_DEVICE_ID`, `VIVADO_JOBS`, `AXI_DATA_WIDTH` (64 or
128), `DEBUG_ILA` (see below).

### Debug build

`DEBUG_ILA=1 ./go.sh` adds one ILA that watches the PCIe bridge's AXI master
and both AXI-Lite slave ports plus the resets and clock locks (details at the
end of `bd.tcl`). It is built around the free BASIC licence, which allows a
single ILA with at most five probe ports and no System ILA on an interface:
`rtl/debug/axi_tap_*.v` are monitor-mode taps that bundle each link into a
few wide vectors. Probe file: `build/canfd.runs/impl_1/canfd_wrapper.ltx`.

## Linux

The design presents PCI ID `1760:ff00`, the ID the mainline driver binds to
(it was written for CTU's own PCIe card; the FPGA implements that card's BAR
layout). Ubuntu and most distributions ship the driver as a module:

```sh
lspci -d 1760:ff00 -v           # should list the card with "Kernel driver in use: ctucanfd_pci"
sudo modprobe ctucanfd_pci      # if it did not autoload
dmesg | grep -i ctucan          # "ctucan_id 0x00000001", "MSI enabled", can0 registered
sudo sw/can-up.sh can0          # 1 Mbit/s nominal, 8 Mbit/s data, FD on
candump can0 &
cansend can0 123##1.DEADBEEF
```

`sw/can-up.sh` sets the bit timing explicitly in quanta rather than with
`bitrate`/`dbitrate` (`ip` then reports 1.25 Mbit/s, the driver's view at its
assumed 100 MHz; the wire rate is 1 Mbit/s). The driver assumes a 100 MHz core clock (hard-coded
in `ctucanfd_pci`), while the core here runs at 80 MHz so that 8 Mbit/s is
reachable at all (100 MHz / 8 MHz = 12.5 quanta is not possible). With
explicit quanta the real rates are exact: 80 tq at 12.5 ns = 1 Mbit/s and
10 tq = 8 Mbit/s, both sampled at 80 %. If you want a different rate,
compute it for 80 MHz and pass `tq 10` with the segment counts.

### Hardware timestamps

The core stamps every received frame with a 64-bit counter (12.5 ns ticks
from the 80 MHz CAN clock), and this design adds a capture block that stamps
transmitted frames with the same counter. Both are captured at the start of
frame: the core's own SOF pulse samples the counter, the RX buffer stores it
(RX_SETTINGS.RTSOP = SOF, set by the driver), and the capture block copies
it into a per-TXT-buffer latch when the core signals transmit-done for that
buffer. A frame that lost arbitration is re-sampled at its retry's SOF, so
the TX stamp is the SOF of the attempt that went through. The mainline driver discards the RX timestamps and
knows nothing of the TX latches, so `sw/driver/` carries the kernel v7.0
driver with a small patch: it keeps the RX stamp, reads the TX latch for the
echo frame, and advertises hardware timestamping through the kernel's
generic CAN helpers. Timestamps are raw hardware time (the counter starts at
FPGA configuration); there is no PTP clock yet.

```sh
cd sw/driver && make -C /lib/modules/$(uname -r)/build M=$PWD modules
sudo ../hwts-load.sh          # swaps the in-tree modules for these, prints ethtool -T
sudo ../can-up.sh can0
candump -H can0               # hardware RX timestamps
sudo ./hwts_test.py can0 10   # TX (error queue) and RX stamps for sent frames
```

The patch detects the capture block by a signature word, so the same modules
work unchanged on hardware without it (timestamping stays software-only).
It also fixes `presume-ack`: mainline maps it to the core's ACF bit
("acknowledge forbidden", the node stops sending ACK), whereas the kernel's
meaning is the core's STM self-test mode (a frame counts as sent without an
ACK). With the fix a single card can test itself: jumper J5 to H5 and bring
the interface up with `loopback on presume-ack on`. Verified 2026-11-05: the
TX and RX stamps of a looped-back frame are identical (before switching to
SOF capture, the EOF-based stamps were exactly one nominal bit apart, the
core committing a received frame at the sixth EOF bit and signalling
transmit-done at the seventh).

The core change is confined to `rtl/ctu_can_fd_top.vhd`, a copy of the
core's top level with the three outputs added; `go.tcl` compiles it into the
core's library in place of the submodule's file, so the submodule stays
pristine. `patches/ctu_can_fd_top.diff` shows the difference.

If you prefer not to use another vendor's PCI ID, build with
`PCI_VENDOR_ID=0x10EE PCI_DEVICE_ID=0xCAFD` and tell the driver about it at
run time (the last field selects the "with ID register" layout):

```sh
sudo modprobe ctucanfd_pci
echo "10ee cafd ffffffff ffffffff 0 0 1" | sudo tee /sys/bus/pci/drivers/ctucanfd_pci/new_id
```

## Design notes

BAR0 (32 KB) is what the driver's `ctucanfd_pci.c` expects from CTU's card:
offset 0x0000 holds an ID word whose low nibble is the number of cores (1),
and 0x4050 is the "Avalon-to-PCIe interrupt enable" register, implemented
here as a real interrupt gate. BAR1 (16 KB) is the CAN core's register map.
`rtl/can_wrap_bd.v` presents it to the block design as an AXI4-Lite slave
and bridges to the core's APB4 port, and answers offsets 0x1000-0x1FFF
itself with the TX timestamp capture block (0x1000 signature `0x54534C46`,
0x1004 counter rate in Hz, 0x1008 latch count, 0x1010 + 8*i the 64-bit stamp
of TXT buffer i). The core's top level gets three extra outputs for this
(`tx_done`, `tx_done_txtb_index`, `sof`, exported from existing internal
signals) via the override `rtl/ctu_can_fd_top.vhd`; `rtl/can_wrap.vhd` instantiates the
core itself, whose RTL is compiled into its own library `ctu_can_fd_rtl`
(the Vivado IP package shipped with the core is out of date relative to its
RTL, so it is not used). `rtl/misc_regs.vhd` also provides the core's 64-bit timestamp
and the LEDs; `rtl/irq_bridge.v` converts the core's
level interrupt into the AXI PCIe bridge's request/grant handshake, with a
re-send every millisecond while the line stays high so a lost edge cannot
hang the driver. `bd.tcl` builds the block design; `go.tcl` drives the
project flow and leaves outputs named like the other projects so CI handles
them identically.

## Status and caveats

- Builds and meets timing in Vivado 2026.1 (x4 Gen1, about 24 % of the
  XC7A100T's LUTs, 17.5 block RAMs). Both the open-source checks and the
  Vivado CI job cover it.
- Expect three critical warnings from the PCIe IP's own constraints failing
  to place the GT lanes in default order: our early constraints win, which
  is required because the LiteFury's M.2 lanes are wired to the GT channels
  out of order (the vendor's sample project does the same).
- Bring-up on a LiteFury (2026-11-03, Linux 7.0, Intel B250 host): the card
  enumerates at x4 Gen1, `ctucanfd_pci` binds, both BAR register maps read
  correctly (BAR0 ID `0x00000001`, core device ID `0x0207CAFD`), the driver's
  interrupt enable works and MSI interrupts arrive. With the design in flash
  the card is up and bound by the driver about five seconds into a cold boot,
  with the firmware assigning the BARs. The CAN bus itself has not been
  exercised yet (no transceiver attached).
- Loopback without a transceiver does not work: the core's loopback mode only
  makes it receive its own frames, it still samples the bits on `can_rx`, so
  a lone node with `can_rx` pulled up goes bus-off with bit errors. For a
  self-test jumper AIO1_P to AIO1_N (`can_tx` to `can_rx`) and bring the
  interface up with `loopback on presume-ack on`.
- If every register reads `0xffffffff` while `lspci` looks fine, the TLPs
  are not reaching the card. Two host-side causes seen during bring-up:
  1. Loading a bitstream over JTAG resets the card's PCIe config space.
     `lspci -vv` then marks the regions `[virtual]`. Re-enumerate:
     `echo 1 > /sys/bus/pci/devices/0000:02:00.0/remove` then
     `echo 1 > /sys/bus/pci/rescan` (adjust the address).
  2. After such a hot re-enumeration the root port's memory window ended up
     disabled in hardware (base `fff0`, limit `0000`) while the kernel
     still believed it was assigned; the exact trigger was not pinned down.
     Check with `setpci -s <root port> MEMORY_BASE MEMORY_LIMIT` and compare
     with `Memory behind bridge` in `lspci -vv`; if they disagree, write the
     window (`MEMORY_BASE.w=0xd000 MEMORY_LIMIT.w=0xd000` for a window at
     `0xd0000000`), or power-cycle with the design in flash so the firmware
     sets everything up.
- MSI is the expected interrupt path. The legacy INTx fallback assumes the
  bridge alternates Assert/Deassert messages per request, which is untested.
- Licence: the CTU CAN FD core is free for non-commercial use only, and any
  CAN implementation used commercially needs a CAN protocol licence from
  Bosch. Fine for a hobby card; read `third_party/CTU-CAN-FD/LICENSE` before
  anything else.
