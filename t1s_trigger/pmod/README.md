# 10BASE-T1S tap Pmod

A small Pmod module that lets the Basys 3 listen to a 10BASE-T1S bus and
brings four trigger outputs to connectors. KiCad 9 project, two layers,
20 x 40 mm.

```
T1S bus (A/B) --> J2 screw terminal / J3 header --> U1 RS-485 receiver --> RX --> Pmod IO1
                                   |- JP1 + R1 (optional 100 R termination)
FPGA TRIG0..3 --> Pmod IO2,IO3,IO4,IO7 --> 33 R --> J5 header; TRIG0 also --> 49.9 R --> J4 SMA
```

The receiver is a 3.3 V, 50 Mbit/s RS-485 transceiver used receive-only. It is
a high-impedance differential input with a wide common-mode range and a
fail-safe output (idle bus reads as logic 1), which is exactly what a passive
monitor tap needs. The 10BASE-T1S differential Manchester signal has at most
one edge every 40 ns, well inside a 50 Mbit/s part. The driver is held off by
R4 unless the FPGA drives IO8 high; `IO9` is the driver data pin so the board
can also inject test patterns if you ever want to (not T1S compliant levels).

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

Standard 12-pin Pmod, 3.3 V. Pmod pins 1 to 6 are the top row, 7 to 12 the
bottom row, looking at the module with the header pointing away from you and
components up. Footprint pad numbers are odd for the top row and even for the
bottom row.

| Pmod pin | Signal | Direction (FPGA) | Note |
|---------:|--------|------------------|------|
| 1 (IO1)  | RX     | in  | receiver output, 3.3 V logic, idles high |
| 2 (IO2)  | TRIG0  | out | to J5 pin 1 via 33 R and to J4 SMA via 49.9 R |
| 3 (IO3)  | TRIG1  | out | to J5 pin 2 via 33 R |
| 4 (IO4)  | TRIG2  | out | to J5 pin 3 via 33 R |
| 5        | GND    |     | |
| 6        | VCC    |     | 3.3 V from the host |
| 7 (IO7)  | TRIG3  | out | to J5 pin 4 via 33 R |
| 8 (IO8)  | DE     | out | driver enable, 10 k pull-down, leave low or unused |
| 9 (IO9)  | TXD    | out | driver data (only matters with DE high) |
| 10 (IO10)| SPARE  | any | test point TP1 |
| 11       | GND    |     | |
| 12       | VCC    |     | 3.3 V |

On the Basys 3 header JA this is JA1 = RX, JA2 = TRIG0, JA3 = TRIG1,
JA4 = TRIG2, JA7 = TRIG3, JA8 = DE, JA9 = TXD, JA10 = spare.

**Check pin 1 before plugging in.** The silkscreen marks Pmod pin 1 (square
pad) and pins 6, 7 and 12 at the row ends. Hold the module next to the Basys 3
JA socket and confirm the square pad lines up with the socket's pin 1 (the
Basys 3 silkscreen marks it); the right-angle header can be soldered on
either face, and a module plugged in upside down puts 3.3 V on signal pins.

## Other connectors

| Ref | What | Pins |
|-----|------|------|
| J2  | 3.5 mm screw terminal | 1 = A, 2 = B (10BASE-T1S pair) |
| J3  | 1x3 0.1" header, same bus in parallel | 1 = A, 2 = B, 3 = GND |
| J4  | SMA, edge mount | TRIG0 through 49.9 R, use a 50 R scope input or a 1 M input (then you get the full 3.3 V) |
| J5  | 1x5 0.1" header | 1 = TRIG0, 2 = TRIG1, 3 = TRIG2, 4 = TRIG3, 5 = GND, each through 33 R |
| JP1 | solder jumper | closed: 100 R (R1) across A/B. Open by default |
| TP1 | test point | Pmod IO10 |
| D1  | green LED | lit while the bus is active (RX low), dark when silent |

## Bill of materials

| Ref | Value | Package | Example part | Notes |
|-----|-------|---------|--------------|-------|
| U1 | SN65HVD78 | SOIC-8 | TI SN65HVD78D | 3.3 V, 50 Mbps, fail-safe RS-485. Alternatives with the same pinout: ADI ADM3065EARZ, Maxim MAX22500EASA. Do not fit a 5 V-only or 500 kbps part |
| C1 | 100 nF | 0603 | any X7R 16 V | decoupling |
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

`out/bom.csv` is the machine-generated version (JP1 and TP1 are excluded as
non-purchasable).

## Assembly and use

- **Keep the stub short.** 10BASE-T1S nodes hang off the mixing segment on
  stubs of a few centimetres at most. Wire J2 or J3 to the bus with the
  shortest twisted pair you can, ideally directly at a bus connector or at
  the end node. The tap adds roughly 20 pF plus the stub to the bus.
- **Termination.** The bus already has 100 R at both ends. Leave JP1 open
  unless this module *is* one end of the bus on your bench. Then close JP1.
- **Polarity.** Differential Manchester does not care which wire is A or B;
  the decoder in the FPGA only looks at edge timing. Swapping A/B inverts RX
  but changes nothing else.
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
terminal block footprints, whose outlines extend past the edge by design.
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
| Size, layers | 20 x 40 mm, 2 layers |
| Thickness, copper | 1.6 mm FR-4, 1 oz |
| Min track / space | 0.25 mm |
| Min hole | 0.3 mm (vias 0.6 / 0.3 mm, 20 of them) |
| Finish | HASL or ENIG, no impedance control, no castellations |

Assembly is hand-solderable: 0603 passives, SOIC-8, and through-hole
connectors. `out/bom.csv` lists the parts with manufacturer part numbers
(the `MPN` table in `tools/netlist.py`, also stored as hidden `Manufacturer`
and `MPN` fields on every symbol and footprint).

For an assembly quote, `tools/pcbway_quote.sh assembly` uploads
`out/t1s_tap_assembly.zip` instead: the gerbers plus `PCBWay_bom.csv`
(designator, quantity, value, footprint, MPN, manufacturer, SMT/THT) and
`PCBWay_positions.csv` (centroids in mm, same origin as the gerbers, all parts
on the top side). On the quote page tick PCB Assembly; it is one side, 16
placements in 13 BOM lines (12 SMT, 4 THT), parts sourced by the fab from the
MPNs, no DNP. JP1 and TP1 are bare copper and are excluded from both files.
The two 0.1" headers and the Pmod header can be swapped for any equivalent;
the SMA footprint is specific to Amphenol 132289 and the terminal block to the
Phoenix PT 1,5/2-3.5-H.
