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
- PCIe x4 at Gen1 (2.5 GT/s). Gen2 works electrically on the LiteFury but
  puts the bridge's AXI clock at 125 MHz, where its unused AXI-to-PCIe
  slave path misses timing by a few tens of picoseconds on the -2L speed
  grade; Gen1 halves that clock and a CAN card needs none of the bandwidth.

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
`PCI_VENDOR_ID` / `PCI_DEVICE_ID`, `VIVADO_JOBS`.

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
`bitrate`/`dbitrate`. The driver assumes a 100 MHz core clock (hard-coded
in `ctucanfd_pci`), while the core here runs at 80 MHz so that 8 Mbit/s is
reachable at all (100 MHz / 8 MHz = 12.5 quanta is not possible). With
explicit quanta the real rates are exact: 80 tq at 12.5 ns = 1 Mbit/s and
10 tq = 8 Mbit/s, both sampled at 80 %. If you want a different rate,
compute it for 80 MHz and pass `tq 10` with the segment counts.

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
and bridges to the core's APB4 port; `rtl/can_wrap.vhd` instantiates the
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
- It has not yet been tested on a LiteFury with a transceiver attached; the first bring-up should check
  `lspci`, then `dmesg` for the driver's BAR/ID messages, then loopback mode
  (`ip link set can0 type can loopback on`) before a real bus.
- MSI is the expected interrupt path. The legacy INTx fallback assumes the
  bridge alternates Assert/Deassert messages per request, which is untested.
- Licence: the CTU CAN FD core is free for non-commercial use only, and any
  CAN implementation used commercially needs a CAN protocol licence from
  Bosch. Fine for a hobby card; read `third_party/CTU-CAN-FD/LICENSE` before
  anything else.
