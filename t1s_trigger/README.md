# 10BASE-T1S trigger monitor (Basys 3)

Listens to a 10BASE-T1S (IEEE 802.3cg, single-pair, multidrop) bus through a
small tap Pmod and raises a trigger pulse for an oscilloscope or logic
analyser when things of interest happen on the wire: PLCA beacons, packet
start, SFD, end-of-stream delimiters, CRC errors, coding errors, or a packet
from a chosen node. The 16 switches choose which events fire the trigger.

```
T1S bus --(tap stub)--> pmod/ (two RS-485 receivers) --> JA1, JA10 --> dme_rx --> t1s_pcs_rx --> events --+--> trigger pulses (JA2..JA7)
                                                                                   plca_track -------------+--> LEDs, 7-segment counters
```

The decoder works from the raw line signal, not from a PHY, so it sees
everything including beacons and commits, which a PHY's MII hides.

## Hardware

- Basys 3 (Artix-7 XC7A35T, 100 MHz oscillator).
- The tap Pmod in [`pmod/`](pmod/README.md) on connector **JA**. It is a
  pair of RS-485 receivers (SN65HVD78) used as high-impedance
  differential-to-logic converters, one with A and B swapped: 10BASE-T1S
  drives about ±1 V differential, well above their thresholds, and their
  fail-safe outputs idle high during bus silence so there is no chatter. RX
  (JA1) goes low while the line is negative, RXN (JA10) while it is positive,
  so the FPGA sees negative / positive / idle and every edge on the wire,
  including the first one of a transmission whichever polarity it starts
  with. Keep the stub from the bus to the Pmod short (a few cm) and leave the
  termination shunt (JP1) off unless the Pmod is the physical end of the bus.
- Trigger outputs are 3.3 V logic pulses on the Pmod's SMA (TRIG0) and pin
  header (TRIG0..3).
- Optional: a Digilent Pmod OLEDrgb on connector **JB** shows every trigger
  with its rate (see below).

## Controls

Switches (SW0 on the right). SW0..SW11 are ORed into TRIG0; each LED below
lights for 50 ms when its event occurs regardless of the switch.

| SW   | TRIG0 fires on                                                              | LED  |
|------|------------------------------------------------------------------------------|------|
| 0    | BEACON (first N symbol of the PLCA beacon)                                   | LED0 |
| 1    | COMMIT (a node holding its transmit opportunity: third consecutive J symbol) | LED1 |
| 2    | SSD, start of a packet on the wire (second H symbol)                          | LED2 |
| 3    | SFD found in the descrambled preamble                                        | LED3 |
| 4    | ESDOK, packet ended normally (T R, or R R in a burst)                        | LED4 |
| 5    | ESDERR, transmitter flagged an error (T K)                                   | LED5 |
| 6    | ESDJAB, jabber (T S, see note on `C_SYM_S` in `rtl/t1s_pkg.vhd`)             | LED6 |
| 7    | burst continuation (R R): the same node sends another packet                 | LED7 |
| 8    | CRC error: packet ended with ESDOK but the FCS is wrong                      | LED8 |
| 9    | protocol error: invalid 5B code, symbol out of place, DME timing violation, transmission cut off, no SFD, ESD without delimiter, runt (< 64 octets) | LED9 |
| 10   | selects the TRIG0 pulse width: off = 100 ns, on = 1 µs                       |      |
| 11   | SSD of a packet sent by PLCA node ID SW15..SW12                              |      |
| 15..12 | node ID (0..15) for SW11                                                   |      |

Other LEDs: LED10 = PLCA synchronised (a beacon was seen in the last 100 ms),
LED11 = line activity, LED15..12 = node ID of the last transmission.

Pmod JA outputs:

| Pin  | Signal   | Meaning                                                   |
|------|----------|-----------------------------------------------------------|
| JA1  | RX       | input from receiver U1, low while the line is negative    |
| JA2  | TRIG0    | switch-selected trigger (SMA on the Pmod)                 |
| JA3  | TRIG1    | BEACON, 100 ns                                            |
| JA4  | TRIG2    | SSD (packet start), 100 ns                                |
| JA7  | TRIG3    | any error (ESDERR, ESDJAB, CRC, protocol, runt), 100 ns   |
| JA8  | DE       | RS-485 driver enable, held low                            |
| JA9  | TXD      | RS-485 driver data, unused                                |
| JA10 | RXN      | input from receiver U2, low while the line is positive    |

Seven-segment display: BTNU/BTND cycle the mode, the lit decimal point shows
which (rightmost = mode 0). BTNC clears the error counters.

| Mode | Shows (hex)                         |
|------|-------------------------------------|
| 0    | good packets per second             |
| 1    | beacons per second                  |
| 2    | CRC errors since reset              |
| 3    | protocol errors + runts since reset |
| 4    | SQI+ (0..1F): left = worst transmission of the last second, right = last transmission |
| 5    | jitter statistic of the last transmission, S·256/N (see below)   |

## OLED status screen (Pmod OLEDrgb on JB)

The 96 x 64 display lists all the switch-selectable triggers with the number
of times each fired in the last second (five digits, saturating at 99999).
An entry is white when its switch is on and grey when it is off, so the
screen shows both what TRIG0 is currently set to fire on and what is
happening on the bus. It refreshes about 60 times a second; the counts step
once a second.

```
100NS ID=5 PLCA     TRIG0 pulse width (SW10), node ID (SW15..12),
BCN12345 JAB    2   PLCA (green: beacons seen in the last 100 ms) or CSMA (grey)
CMT    7 BRS    3
SSD99999 CRC    4   BCN beacon, CMT commit, SSD packet start, SFD, EOK/EER/JAB
SFD    0 PRT    5   end of packet ok/error/jabber, BRS burst, CRC CRC error,
EOK   64 ID5   60   PRT protocol error or runt, ID5 packets from node 5 (SW11)
EER    1 TRG99999   TRG: TRIG0 pulses actually produced (always cyan)
ERR    8 HB     9   ERR: any error, as on JA7 (cyan); HB: heartbeat runs
================.   bottom pixel row: SQI+ bar, 3 px per step (green >= 24,
                    yellow >= 12, red below) on a dim track, white mark at the
                    worst SQI+ of the last second
```

The simulation in `sim/tb_oled.vhd` decodes the SPI stream and writes the
frame to `sim/oled_frame.ppm`; `python3 sim/ppm2png.py sim/oled_frame.ppm
frame.png` turns it into a picture (the layout above is from it).

Wiring: Pmod OLEDrgb straight into JB (pin 1 = CS at JB1). The driver
`rtl/oled_ssd1331.vhd` follows Digilent's power-up sequence (PMODEN, reset,
init table, VCCEN, display on) and streams RGB565 pixels at 6.25 MHz; the
text comes from `rtl/trig_screen.vhd` (5 x 7 font in `rtl/oled_font_pkg.vhd`,
generated from ASCII art by `tools/gen_font.py`), the counts from
`rtl/bcd_rate.vhd`.

## Trigger timing

Events are recognised when the symbol that defines them is complete, so the
pulse comes a fixed delay after the event on the wire: about 0.45 µs after the
first edge of a beacon (one 5B symbol plus pipeline), about 30 ns after the
last edge of an SSD, SFD or ESD symbol. CRC errors are known at ESDOK, i.e. at
the end of the packet. The last bit of a transmission has no edge after it;
it is complete about 60 ns after the line is released, which the two receivers
see directly, so events that end a transmission (ESD, heartbeat) come 100 to
140 ns after the last edge on the wire. The delay is constant, so set the
scope's trigger delay once.

## Signal quality from timing jitter (SQI+)

Every transmission gets a signal-quality figure on the same 0..31 scale as
the LAN8670 Rev D0's OPEN Alliance "DCQ SQI+" register (see
`arb/README.md`: on the bench that PHY reports SQI+ ≈ 33 − 8.8·σ for Gaussian
edge jitter σ in ns rms), but per frame instead of after a measurement
window, and visible on the seven-segment display (modes 4 and 5).

- `rtl/clk_gen.vhd`: an MMCM makes 250 MHz, 250 MHz + 90° and an aligned
  125 MHz from the 100 MHz oscillator.
- `rtl/oversample_in.vhd`: each receiver pin goes through an ISERDESE2 in
  oversampling mode, which samples it at 0/90/180/270° of the 250 MHz clock,
  i.e. every 1 ns; two periods are gathered into eight samples per 125 MHz
  clock so the arithmetic has an 8 ns budget. The ISERDES pass-through output
  feeds the existing 100 MHz decoder, so nothing else changes.
- `rtl/edge_time.vhd` (125 MHz): timestamps every receiver assertion,
  classifies each interval as a half (40 ns) or full (80 ns) cell, takes its
  error e against nominal and the difference d between e and the previous e
  of the same kind (half/full × edge polarity). Differences cancel
  duty-cycle distortion, the delay mismatch between the two receivers and the
  transmitter's clock offset, so no mean has to be subtracted. It sums d² and
  counts, and hands S and N over at the end of the transmission (192 ns
  without an edge).
- `rtl/sqi_calc.vhd` (100 MHz): var(d) = 4σ² + 1/3 ns² for edge jitter σ and
  1 ns sampling, so SQI+ is the largest k with S < N·(4σ_k² + 1/3),
  σ_k = (33 − k)/8.8 ns: at most 32 multiply-and-compare steps, no division.
  A generic `SQI_FLOOR2_X256` (σ_floor² × 256) subtracts the receivers' own
  jitter once it has been measured against a PHY on a clean signal. The
  divider that produces S·256/N for mode 5 is for that calibration: on a
  clean line it reads about 0x55 (1/3 × 256); the floor is (value − 0x55)/4.
- `sim/tb_sqi.vhd`: a jittered DME transmitter checks the scale: σ = 0, 0.5,
  1, 2, 3, 4 ns give 31, 28, 24, 15, 7, 0, and a 4 ns receiver skew changes
  nothing. Transmissions shorter than 64 intervals are ignored.

Status: simulated (GHDL, behavioural clocks and samplers via the `G_SIM`
generic), not yet built or tried on the board. Things to check on the first
Vivado build: the ISERDESE2 oversample timing (the four outputs are
re-registered on the 250 MHz clock; Q4 changes only 1 ns before that edge),
the 250 → 125 MHz hand-off register in `oversample_in.vhd` (a related-clock
path with a 4 ns budget), the MMCM/BUFG placement, and `set_clock_groups` in
`constraints/top_timing.xdc`.
On hardware, compare mode 4 against `tools/t1s0_phy_regs.py --dcq` on the
host PHY while `tools/sqi_sweep.py` steps the generator's jitter; the
receivers' floor then goes into `SQI_FLOOR2_X256`.

## How it decodes

- `rtl/dme_rx.vhd`: samples both receiver outputs at 100 MHz, takes an edge
  whenever either one asserts (exactly one does for every transition on the
  wire), and measures the time between edges. Every 80 ns bit cell starts
  with a transition; a 1 has another one 40 ns later. Both outputs high for
  30 ns means the line was released, which closes the last cell and is
  SILENCE; the first edge after SILENCE is a symbol boundary. A line held at
  one level for 160 ns counts as silent too.
- `rtl/t1s_pcs_rx.vhd`: assembles 5B symbols (LSB first) and follows the
  transmission: `J J H H`, nine discarded symbols while the x^17+x^14+1
  self-synchronising descrambler locks, preamble nibbles 5 until the SFD
  nibble D, data (low nibble of each octet first) with a running Ethernet
  CRC-32, then `T R` / `T K` / `T S` / `R R`. BEACON is a run of N symbols,
  COMMIT a run of J, a run of T from silence is heartbeat/suspend signalling.
- `rtl/plca_track.vhd`: after a beacon, counts transmit opportunities
  (32 bit times of silence each, or one per transmission) to attribute each
  packet to a PLCA node ID.
- `rtl/top.vhd`: switches, LEDs, display, pulse stretching.
- `rtl/oled_status.vhd`: the OLED subsystem (rate counters, text screen, SSD1331 driver).

Constants (symbol codes, timings, PLCA defaults) are in `rtl/t1s_pkg.vhd`
with their sources. The ESDJAB symbol value is the one thing not confirmed
from public documents; a wrong guess only moves jabber from the ESDJAB
event to the protocol-error event.

Known limits: node IDs assume the default `to_timer` of 32 bit times and a
node that pauses within a burst for longer than 160 ns is counted as the next
ID; on a CSMA/CD (non-PLCA) segment node IDs are meaningless (LED10 off).
Symbol alignment trusts the first edge after silence, which is why the tap
has two receivers (rev A/B had one and missed the first edge of transmissions
starting with a positive half bit; see Polarity in `pmod/README.md`).
Data-dependent triggers (addresses, payload patterns) are not implemented.

## Build and test

```sh
cd t1s_trigger
./go.sh                                   # Vivado: synth, place, route, bitstream, program over JTAG
CI=1 ./go.sh                              # build only
docker run --rm -v "$PWD/..":/src -w /src/t1s_trigger hdlc/ghdl:yosys sim/run.sh   # testbenches
```

`sim/tb_top.vhd` contains a behavioural 10BASE-T1S transmitter (DME, 4B/5B,
scrambler, FCS) driving a model of the two fail-safe receivers, alternates the
polarity each transmission starts with, and exercises beacons, transmit-opportunity counting, commit,
good/bad FCS, ESDERR, ESDJAB, bursts, runts, invalid symbols, truncated
transmissions, DME violations, heartbeat and the switch gating and pulse
widths. `sim/tb_oled.vhd` checks the OLED power-up sequence and the rendered
frame. Both are run by `ci/check.sh`; the Vivado workflow builds the bitstream.

### Waveforms

```sh
docker run --rm --user "$(id -u)" -v "$PWD/..":/src -w /src/t1s_trigger hdlc/ghdl:yosys sim/run.sh --wave
gtkwave sim/tb_top.ghw sim/tb_top.gtkw    # or --vcd and any VCD viewer (Surfer, VS Code WaveTrace, ...)
```

GTKWave opens with an empty wave panel: the `.gtkw` save files (`sim/tb_top.gtkw`,
`sim/tb_oled.gtkw`) preload the line, decoder, event and trigger signals. To
add more, expand `top` > `tb_top` in the tree at the top left, click an
instance, and drag signals from the list below it into the wave panel (or
Search > Signal Search Regexp). Right-click a vector > Data Format to switch
between binary, hex and decimal. `sim/t1s_symbols.txt` is a GTKWave translate
filter that shows a 5B code as its symbol name (`J SYNC / COMMIT`, `H SSD`,
data nibbles as `0`..`F`); the tb_top save file applies it to `sym_q` in the
PCS, which holds the last complete symbol (`sym_valid` pulses when it lands;
`sym_sr` is the shift register filling up behind it; `dnib_q`/`dnib_valid`
do the same for the descrambled data nibble). The filter can be put
on any 5-bit signal with Data Format > Translate Filter File.

`--wave` writes `sim/tb_top.ghw` and `sim/tb_oled.ghw` (GHDL's own format:
small, keeps records and enums such as the PCS state); `--vcd` writes VCD
(10x bigger, bits and vectors only). Without a viewer, `sim/vcd2svg.py` draws
a window of chosen signals as an SVG for a browser or editor:

```sh
python3 sim/vcd2svg.py sim/tb_top.vcd -l                    # list signal names
python3 sim/vcd2svg.py sim/tb_top.vcd ssd.svg -f 11.9us -t 13.3us \
    line_p line_n dut_core.u_dme.bit_valid dut_core.u_dme.bit_val dut_core.u_pcs.sym_sr dut_core.ev_ssd
```

Names are matched by their tail, so `u_dme.start` is enough as long as it is
unambiguous (`dut_core.` and `dut_top.u_mon.` both contain a decoder).

## Sources

- IEEE 802.3cg Clause 147 drafts on ieee802.org (comment resolution r2.0,
  Sept 2018; D0.3, Nov 2017): 4B/5B table, DME rules, scrambler, PCS state
  machines, PLCA timers.
- OPEN Alliance 10BASE-T1S PCS compliance test suite v1.0 and TC14/TC10
  sleep/wake specification 1.0: final symbol names (SSD = H, ESDOK/ESDBRS = R,
  ESD/HB/SUSPEND = T), packet structure, nine-symbol descrambler lock.
- Microchip LAN867x datasheet: PMA transmitter 0.8–1.2 V differential,
  receiver input impedance and capacitance.
