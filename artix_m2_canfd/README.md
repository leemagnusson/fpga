# artix_m2_canfd: M.2 2280 Artix-7 card with four CAN FD transceivers

A 22 x 80 mm M.2 key-M card (PCIe x4 Gen2) around an AMD Artix-7 XC7A50T
with four CAN FD transceivers, intended to run the `litefury_canfd` design
in this repo extended to four cores. The whole KiCad project is generated
by `gen/build.py`; edit the Python, not the KiCad files.

```
python3 gen/build.py          # regenerates *.kicad_sch, *.kicad_pcb, lib/, bom.csv
```

## Design

| Block | Part | Notes |
|---|---|---|
| FPGA | XC7A50T-2CSG325I | 15 x 15 mm, 0.8 mm BGA, 4 GTP transceivers. XC7A35T and XC7A100T in CSG325 are drop-in |
| Host interface | M.2 2280 key M card edge | PCIe x4 to GTP bank 216, REFCLK AC-coupled to MGTREFCLK0, PERST# to an I/O, CLKREQ# tied low |
| CAN FD | 4 x MCP2562FD (DFN-8) | 8 Mbit/s, 5 V supply with 3.3 V I/O, ESD diode and optional 120 ohm termination (DNP) per bus |
| CAN connectors | 2 x Hirose DF52-6S-0.8H | 1.5 mm high, at the far end either side of the mount notch; each carries two buses as CANH, CANL, GND |
| Configuration | W25Q128JV (WSON-8), QSPI x4, M[2:0] = 001 | Tag-Connect TC2050 pads for JTAG, no connector |
| Clock | 100 MHz 3.3 V oscillator (ECS-2520MV) on an MRCC pin | 200 MHz LVDS not needed; the FPGA design's clock wizard takes 100 MHz |
| VCCINT/VCCBRAM 1.0 V | TPS62823 buck, 3 A | first rail up |
| VCCAUX 1.8 V | TLV62569 buck, 2 A | enabled by the 1.0 V power-good |
| MGTAVCC 1.0 V, MGTAVTT 1.2 V | TLV75510 / TLV75512 LDOs from 1.8 V | low noise for the transceivers |
| VCCO 3.3 V | TPS22918 load switch from the M.2 3.3 V | enabled ~10 ms after 1.8 V, slew limited: gives the recommended VCCINT, VCCAUX, VCCO order |
| 5 V (CAN) | TPS61023 boost from 3.3 V | enabled with the 3.3 V rail |
| LEDs | 4 user (bank 34) + power | active low, 0402 |

The FPGA pin assignment is generated from the AMD package file
(`gen/data/xc7a50tcsg325pkg.txt`): PCIe lanes in physical order on the GTP
channels, user I/O (12 CAN signals, 4 LEDs) on bank 34, the oscillator and
PERST# on bank 15 clock-capable pins, QSPI on the bank 14 configuration
pins. All I/O banks run at 3.3 V.

Stackup: 6 layers, 0.8 mm (M.2 requirement), signal / ground / power /
power / ground / signal, ENIG. The 0.8 mm BGA fans out with 0.2/0.45 mm
vias on the pad diagonals and 0.1 mm traces.

### M.2 pin mapping

From the PCIe M.2 specification rev 1.0, table 48 (socket 3, key M) and
figures 16/17. The table names pins from the host's side: `PETp/n` is the
host transmitter, so it connects to the FPGA receivers, and `PERp/n` (host
receiver) is driven by the FPGA transmitters through 100 nF AC coupling
capacitors on the card. REFCLK is AC coupled too. Pins 59-66 are the key.
The card-edge geometry (0.5 mm pitch, 38 top pads 2.0 mm long, 37 bottom
pads 2.5 mm long staggered by 0.25 mm, fingers centred on the 19.85 mm
wide connector tongue, pin 1 at the right in the top view, key slot
1.2 x 3.5 mm next to pin 75, 3.5 mm semicircular mount notch centred on
the far edge) is in `gen/footprints.py` (`M2_*` constants) and the outline
in `gen/pcb.py`.

## Routing flow

The generator places parts and draws the planes; `gen/route.py` escapes the
BGA, adds the fan-out and hands the rest to Freerouting:

```sh
python3 gen/build.py                 # regenerate schematic, board, libraries
python3 gen/route.py prepare         # BGA escapes + dog-bone vias for every used ball, stitching
                                     # vias for plane-net pads, planes filled, build/*.dsn written
java -jar freerouting.jar -de build/artix_m2_canfd.dsn -do build/artix_m2_canfd.ses -mp 400
python3 gen/route.py import          # pull the routes back in, refill planes, save the board
kicad-cli pcb drc --severity-all artix_m2_canfd.kicad_pcb
```

Use Freerouting 1.9.0 (it needs a display: `xvfb-run -a java -jar ...` on a
headless machine). The 2.x releases ignore `-mp` in headless mode and only
write the session file when their own improvement heuristic gives up, which
can take hours. Twelve passes take about ten minutes.

Freerouting cannot get signals out of a 0.8 mm BGA once the plane vias are
in, so `gen/escape.py` does that deterministically before the export: outer
ring balls leave straight out on the top layer, second-ring balls through the
free row gap beside them, and deeper balls drop to the bottom layer and run
along the pad-row/column lines (every cell-centre via clears those lines by
exactly 0.15 mm) to one pitch outside the package. Plane balls get a via in
any free cell around them, or hop to a neighbouring ball of the same net;
the two 1.8 V balls over the 1.0 V strip get a short bottom-layer run to a
cell over the 1.8 V plane. The PCIe receive pairs and REFCLK are planned
first, as pairs: a backtracking search tries adjacent exit lines (south
column lines, or east/west row lines either side of a transmit pair) for
both halves of each pair, deepest pair first, and rejects any placement
that would strand the corner's other signals (JTAG, QSPI). The result:
RX0, RX2 and REFCLK leave south on adjacent bottom-layer lines, RX1
straight down on the top layer, RX3 east on the row lines either side of
TX1, and the transmit pairs east on their row line and the row gap beside
it. The search takes about ten minutes. Everything added by `prepare` is
locked, which the DSN export turns into fixed wires that the autorouter
leaves alone.

Planes (6 layers, 0.8 mm): L2 and L5 ground; L3 3.3 V everywhere; L4 1.8 V
with a 1.0 V strip from the core balls up to the buck, the 3.3 V input
under the fingers and along the right edge to the regulators, 5 V at the
CAN end, and the two transceiver rails at the GTP corner, each extended
below the package under its decoupling zone and joined to the corner
island by a locked 0.1 mm B.Cu link threaded through the escape via row
(`pcb.LINKS`). Plane fills use 0.1 mm clearance and width so the islands
survive the 0.4 mm vias on the 0.8 mm cell grid. A 0.3 mm
keep-out ring keeps routed copper off the edge. The M.2 fingers, pads
beyond their planes, and the FPGA's signal balls are left to the router.

After the autorouter, re-route the eight PCIe pairs and REFCLK by hand as
coupled pairs: Freerouting routes each net on its own.

## Files

- `gen/design.py`: the circuit as parts, pins and nets, with datasheet pin
  numbers quoted at the top of the file.
- `gen/footprints.py`: every footprint used, generated from vendor land
  patterns, so nothing depends on the KiCad library version.
- `gen/symbols.py`, `gen/schematic.py`, `gen/pcb.py`: writers for the
  symbol library, the schematic sheets and the board (zones, planes, placement).
- `gen/escape.py`, `gen/fanout.py`, `gen/route.py`: BGA escapes, plane fan-out and the
  Freerouting round trip.
- `lib/`: generated symbol and footprint libraries (project-local tables
  `sym-lib-table` and `fp-lib-table` point at them). Footprints reference
  the official KiCad 9 3D models (`KICAD9_3DMODEL_DIR`) where one matches
  the land pattern; the oscillator, the FPGA, the small VSON and the Hirose
  headers get plain box models written to `lib/artix_m2_canfd.3dshapes`.
- `bom.csv`: references, values, manufacturer part numbers.

The schematic is a labelled netlist: each part is drawn with a global
label on every pin, split over five sheets (M.2/PCIe, FPGA I/O and
configuration, FPGA power, supplies, CAN). It is complete and checkable but
not pretty; the PCB is placed but not routed.

## Status and what to check before ordering

Generated, electrical rule check clean, design rule check clean apart from
the unrouted connections (KiCad 9.0.8). KiCad's own netlist export of the
schematic matches the Python design net for net. Not built or tested.
Parts are auto-placed into zones (the PCIe coupling capacitors are fixed
in line with their fingers, pads along the trace, P and N set 0.4 mm
outward so both jog the same amount, with the PCIe-zone resistors beside them;
configuration above the FPGA, power above that, CAN at the far end; on the
back the FPGA decoupling just beyond the BGA in one zone per rail so every
capacitor sits over its plane, the transceiver-rail decoupling below the
GTP corner, then the LEDs, feedback dividers and CAN terminations). Zones
stop 3 mm short of the long edges so each side keeps a routing corridor on
both layers; treat the placement as a starting point.
Note that `kicad-cli` ignores the `.kicad_dru` rule file, so the project
file carries a 0.1 mm copper-to-edge minimum for the gold fingers and the
rule file restores 0.3 mm for everything else when the GUI is used.

Review list, most important first:

1. **Routing** is yours: BGA fan-out, the four PCIe pairs (100 ohm
   differential, length-matched within a pair), REFCLK, and the power
   planes. The placement is a starting point.
2. **MGTRREF resistor**: 100 ohm 1 % to ground is used, as on other Xilinx
   7 series boards, but I could not open UG482 to confirm the GTP value.
   Verify in UG482 "Termination resistor calibration circuit" before
   ordering.
3. **Hirose DF52 footprint**: pad geometry now follows the KiCad library
   footprint (drawn from the Hirose drawing); the connectors are placed so
   the cable exits off the end of the card. Still worth a look at the
   DF52-6S-0.8H(21) drawing before ordering.
4. **Oscillator**: ECS-2520MV pad numbering is counter-clockwise from the
   chamfered corner; the footprint follows the datasheet land pattern.
   SiTime SiT8008 in 2520 is a drop-in if ECS is out of stock.
5. **MCP2562FD DFN land pattern** is generic 3 x 3 mm 0.65 mm pitch; check
   against the Microchip drawing.
6. **Height**: everything on top is under 1.5 mm (FPGA 1.5 mm, DFN/WSON
   0.8-1.0 mm, SOT-23 1.3 mm, inductors 1.0 mm). The bottom carries 0402s,
   three 0805s (up to 1.25 mm) and the LEDs. This suits a desktop M.2
   slot; a laptop slot with a 1.35 mm bottom limit needs the 0805s moved.
7. **Licensing/IP**: the CTU CAN FD core is non-commercial; four instances
   fit the 50T comfortably (one core plus PCIe used 24 % of a 100T).
