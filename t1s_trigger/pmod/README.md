# 10BASE-T1S tap Pmod

A small Pmod module that lets the Basys 3 listen to a 10BASE-T1S bus and
brings four trigger outputs to connectors. KiCad 9 project, two layers,
20 x 46 mm.

```
T1S bus (A/B) --> J2 screw terminal / J3 header --> U1 RS-485 receiver -------------> RX  --> Pmod IO1  (low: line negative)
                                   |---------------> U2 RS-485 receiver, A/B swapped --> RXN --> Pmod IO10 (low: line positive)
                                   |- JP1 (shunt) + R1: optional 100 R termination
FPGA TRIG0..3 --> Pmod IO2,IO3,IO4,IO7 --> 33 R --> J5 header; TRIG0 also --> 49.9 R --> J4 SMA
```

The receivers are 3.3 V, 50 Mbit/s RS-485 transceivers used receive-only:
high-impedance differential inputs with a wide common-mode range and a
fail-safe output (idle bus reads as logic 1), which is what a passive monitor
tap needs. The 10BASE-T1S differential Manchester signal has at most one edge
every 40 ns, well inside a 50 Mbit/s part. There are two of them because one
cannot tell idle from positive: the fail-safe thresholds sit at about -20 and
-200 mV, so the output only changes when the line crosses about -0.1 V. U2 has
A and B swapped and so only reacts to crossings of about +0.1 V. Together they
give the FPGA three states, negative (RX low), positive (RXN low) and idle
(both high), and every transition on the wire, including the first one out of
idle whichever polarity it has, asserts exactly one of the two outputs. U1's
driver is held off by R4 unless the FPGA drives IO8 high; `IO9` is the driver
data pin so the board can inject test patterns if you ever want to (not T1S
compliant levels). U2's driver pins are grounded.

## Files

| File | What |
|------|------|
| `t1s_tap.kicad_pro`, `t1s_tap.kicad_sch`, `t1s_tap.kicad_pcb` | the KiCad 9 project |
| `t1s_tap.kicad_sym`, `sym-lib-table` | project symbol library (transceiver symbol) |
| `tools/netlist.py` | the circuit as data: parts, footprints, pin to net. Schematic and board are both generated from it |
| `tools/gen_sch.py`, `tools/gen_pcb.py` | generators (schematic as s-expressions, board through the pcbnew API) |
| `tools/build.sh` | regenerates everything and runs ERC, DRC, schematic parity, a pad/net cross-check and all exports |
| `tools/pcbway_quote.sh` | uploads the gerber zip (or, with `assembly`, gerbers + BOM + placement) to PCBWay and prints a link to a pre-filled instant quote |
| `tools/pcbway_files.py` | writes `out/PCBWay_bom.csv`, `out/PCBWay_positions.csv` (the layout PCBWay's KiCad plugin uses) and `out/t1s_tap_assembly.zip` |
| `3dmodels/` | STEP models for every part (copied from kicad-packages3D, CC-BY-SA 4.0); the board references them as `${KIPRJMOD}/3dmodels/` so the 3D view works without the global library |
| `out/` | ERC and DRC reports (JSON), schematic PDF/SVG, board SVG and PNG renders, 3D renders (`pcb_3d.png`, `pcb_3d_rear.png`), `t1s_tap.step` (board with components, for mechanical checks), `bom.csv` (with manufacturer part numbers), `positions.csv`, `gerbers/`, `t1s_tap_gerbers.zip` and `t1s_tap_assembly.zip` |

Everything runs in the `kicad/kicad:9.0` Docker image, no local KiCad needed:

```sh
tools/build.sh
```

## Pmod pinout (J1)

Standard 12-pin Pmod, 3.3 V. Pmod pins 1 to 6 are the upper row, 7 to 12 the
lower row. Looking at the module with the header pointing away from you and
components up, pin 1 is at the **right** end of the upper row and pin 6 at the
left (Digilent Pmod Interface Specification 1.3.1, figure 2; Basys 3 reference
manual figure 20 shows the matching socket, front view, pin 1 top right). The
KiCad footprint numbers its pads the other way round, pad 1 at the left in that
view, so `tools/netlist.py` maps Pmod pin *n* to pad 13-2*n* (pins 1 to 6) and
26-2*n* (pins 7 to 12), and `gen_pcb.py` moves the square pad and the pin-1
tick to Pmod pin 1. Rev A had the header mirrored; plugged into a Basys 3 it
would have put 3.3 V and ground on JA signal pins.

| Pmod pin | Signal | Direction (FPGA) | Note |
|---------:|--------|------------------|------|
| 1 (IO1)  | RX     | in  | U1 output: low while the line is negative, idles high |
| 2 (IO2)  | TRIG0  | out | to J5 pin 1 via 33 R and to J4 SMA via 49.9 R |
| 3 (IO3)  | TRIG1  | out | to J5 pin 2 via 33 R |
| 4 (IO4)  | TRIG2  | out | to J5 pin 3 via 33 R |
| 5        | GND    |     | |
| 6        | VCC    |     | 3.3 V from the host |
| 7 (IO7)  | TRIG3  | out | to J5 pin 4 via 33 R |
| 8 (IO8)  | DE     | out | driver enable, 10 k pull-down, leave low or unused |
| 9 (IO9)  | TXD    | out | driver data (only matters with DE high) |
| 10 (IO10)| RXN    | in  | U2 output: low while the line is positive, idles high |
| 11       | GND    |     | |
| 12       | VCC    |     | 3.3 V |

On the Basys 3 header JA this is JA1 = RX, JA2 = TRIG0, JA3 = TRIG1,
JA4 = TRIG2, JA7 = TRIG3, JA8 = DE, JA9 = TXD, JA10 = RXN.

**Check pin 1 before plugging in.** The silkscreen marks Pmod pin 1 (square
pad with a tick) and pins 6, 7 and 12 at the row ends. Hold the module next to
the Basys 3 JA socket and confirm the square pad lines up with the socket's
pin 1 (the Basys 3 silkscreen marks it); the right-angle header can be soldered
on either face, and a module plugged in upside down puts 3.3 V on signal pins.

## Other connectors

| Ref | What | Pins |
|-----|------|------|
| J2  | 3.5 mm screw terminal | 1 = A, 2 = B (10BASE-T1S pair) |
| J3  | 1x3 0.1" header, same bus in parallel | 1 = A, 2 = B, 3 = GND |
| J4  | SMA, edge mount | TRIG0 through 49.9 R, use a 50 R scope input or a 1 M input (then you get the full 3.3 V) |
| J5  | 1x5 0.1" header | 1 = TRIG0, 2 = TRIG1, 3 = TRIG2, 4 = TRIG3, 5 = GND, each through 33 R |
| JP1 | 1x2 0.1" header + shunt | shunt fitted: 100 R (R1) across A/B. Ship without the shunt |
| D1  | green LED | lit while the bus is active (RX low), dark when silent |

## Bill of materials

| Ref | Value | Package | Example part | Notes |
|-----|-------|---------|--------------|-------|
| U1, U2 | SN65HVD78 | SOIC-8 | TI SN65HVD78D | 3.3 V, 50 Mbps, fail-safe RS-485. Alternatives with the same pinout: ADI ADM3065EARZ, Maxim MAX22500EASA. Do not fit a 5 V-only or 500 kbps part. Fit the same part in both places |
| C1, C2 | 100 nF | 0603 | any X7R 16 V | decoupling |
| R1 | 100 R | 0603 | 1 % | termination, only with JP1 closed |
| R2 | 49.9 R | 0603 | 1 % | SMA source termination |
| R3 | 1 k | 0603 | | LED |
| R4 | 10 k | 0603 | | DE pull-down |
| R5 to R8 | 33 R | 0603 | | trigger series resistors |
| D1 | green | 0603 LED | | activity |
| J1 | 2x6 right-angle male 0.1" | | e.g. Sullins PRPC006DBAN-M71 or any 2x6 right angle | Pmod plug |
| J2 | 2-pos 3.5 mm screw terminal | | Phoenix PT 1,5/2-3,5-H (1984617) | bus |
| J3 | 1x3 male 0.1" | | | bus, header |
| J4 | SMA edge mount | | Amphenol 132289 | TRIG0 |
| J5 | 1x5 male 0.1" | | | triggers |
| JP1 | 1x2 male 0.1" | | Sullins PRPC002SAAN-RC plus a 2.54 mm shunt, e.g. Sullins SPC02SYAN | termination select |

`out/bom.csv` is the machine-generated version (the shunt for JP1 is a loose
part and not in it).

## Assembly and use

- **Keep the stub short.** 10BASE-T1S nodes hang off the mixing segment on
  stubs of a few centimetres at most. Wire J2 or J3 to the bus with the
  shortest twisted pair you can, ideally directly at a bus connector or at
  the end node. The tap adds roughly 30 pF (two receiver inputs) plus the
  stub to the bus.
- **Termination.** A 10BASE-T1S mixing segment has exactly two 100 R
  terminations, one at each end; everything else hangs off it on short stubs.
  Leave the JP1 shunt off unless this module *is* one end of the bus on your
  bench, then fit it. A third termination in the middle halves the signal and
  reflects.
- **Coupling.** Real nodes sit on the bus through 100 nF series capacitors
  on both wires (Microchip AN1718 bus interface network, OPEN Alliance
  10BASE-T1S implementation specification), and the end terminations are
  2 x 50 R with the centre tap to ground through 100 nF in parallel with
  100 k. So the bus carries no DC and its common mode is only loosely
  defined. The tap is DC coupled anyway: the receiver draws no DC worth
  mentioning (1/8 unit load, about 96 k), its -7 to +12 V common-mode range
  covers any offset between the tap and the bus, and its fail-safe bias sets
  the idle level by itself, which series capacitors would need an extra bias
  network to restore. R1 is a plain 100 R; the split version (2 x 49.9 R plus
  100 nF and 100 k from the centre to ground) adds common-mode termination
  that matters for EMC in a vehicle harness, not on a bench.
- **Polarity.** Differential Manchester does not care which wire is A or B;
  the decoder in the FPGA only looks at edge timing. Swapping A/B at J2 just
  exchanges the roles of RX and RXN, which the decoder does not care about
  either. (This is why there are two receivers: rev A/B had one, whose
  fail-safe thresholds both sit below 0 V, so idle and +1 V read the same and
  a transmission starting with a positive half bit had no visible first edge.
  The decoder aligns 5B symbols on the first edge after silence, so it then
  decoded everything one bit late. With the testbench's line model behaving
  like a single receiver, every check failed for positive-first transmissions;
  the standard leaves the start polarity to the PHY.)
- **Scope trigger.** J4 carries TRIG0 through 49.9 R. Into a 50 R scope input
  you get about 1.6 V, into 1 M about 3.3 V. The J5 pins are 3.3 V logic
  through 33 R for a logic analyser.
- **Ground.** The SMA shell, J3 pin 3 and J5 pin 5 are all board ground,
  which is the Basys 3 ground. Bus common mode is handled by the receiver
  (-7 to +12 V), no ground connection to the bus is needed.
- Solder the header on the component side with the pins pointing away from
  the board edge; the footprint body outline on the silkscreen shows where
  the plastic sits.

## Design checks

`tools/build.sh` ends with ERC and DRC summaries. Current state: ERC 0
violations; DRC 0 errors, 0 unconnected, schematic parity clean; the only
warnings are "silkscreen clipped by board edge" from the Pmod header and
terminal block footprints, whose outlines extend past the edge by design, and
two "does not match library" notes for J1 (square pad moved to Pmod pin 1) and
JP1 (courtyard trimmed to the real header body so it fits between the terminal
block and U2).
The script also exports the schematic netlist and verifies every pad net on
the board against it and against `tools/netlist.py`.

## Ordering

`tools/build.sh` leaves `out/t1s_tap_gerbers.zip` (RS-274X gerbers plus Excellon
drill files, plated and non-plated separate). `tools/pcbway_quote.sh` uploads
it to PCBWay through the endpoint their KiCad plugin uses and prints a link to
the instant-quote page with the file attached; log in there to save or order.
Any fab's defaults cover the board:

| Parameter | Value |
|-----------|-------|
| Size, layers | 20 x 46 mm, 2 layers |
| Thickness, copper | 1.6 mm FR-4, 1 oz |
| Min track / space | 0.25 mm |
| Min hole | 0.3 mm (vias 0.6 / 0.3 mm, 26 of them) |
| Finish | HASL or ENIG, no impedance control, no castellations |

Assembly is hand-solderable: 0603 passives, SOIC-8, and through-hole
connectors. `out/bom.csv` lists the parts with manufacturer part numbers
(the `MPN` table in `tools/netlist.py`, also stored as hidden `Manufacturer`
and `MPN` fields on every symbol and footprint).

For an assembly quote, `tools/pcbway_quote.sh assembly` uploads
`out/t1s_tap_assembly.zip` instead: the gerbers plus `PCBWay_bom.csv`
(designator, quantity, value, footprint, MPN, manufacturer, SMT/THT) and
`PCBWay_positions.csv` (centroids in mm, same origin as the gerbers, all parts
on the top side). On the quote page tick PCB Assembly; it is one side, 19
placements in 14 BOM lines (14 SMT, 5 THT), parts sourced by the fab from the
MPNs, no DNP. The JP1 shunt is a loose part.
The two 0.1" headers and the Pmod header can be swapped for any equivalent;
the SMA footprint is specific to Amphenol 132289 and the terminal block to the
Phoenix PT 1,5/2-3.5-H.

## Revision history

- **C** (2026-10-31): second receiver U2 with A/B swapped on Pmod IO10 (was
  a spare/test point), so the FPGA sees negative, positive and idle and never
  misses the first edge of a transmission; board 6 mm longer, U1 and the lower
  half moved down to make room. Needs the rev C FPGA design (`dme_rx` with
  two inputs; JA10 became an input).
- **B** (2026-10-31): Pmod header pin order mirrored (rev A had pin 1 at the
  wrong end of the row, see the pinout section); termination jumper is a 1x2
  header with a shunt instead of a solder jumper; lower half of the board
  re-routed to suit.
- **A** (2026-10-30): first layout, not built.
