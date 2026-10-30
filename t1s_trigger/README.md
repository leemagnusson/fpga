# 10BASE-T1S trigger monitor (Basys 3)

Listens to a 10BASE-T1S (IEEE 802.3cg, single-pair, multidrop) bus through a
small tap Pmod and raises a trigger pulse for an oscilloscope or logic
analyser when things of interest happen on the wire: PLCA beacons, packet
start, SFD, end-of-stream delimiters, CRC errors, coding errors, or a packet
from a chosen node. The 16 switches choose which events fire the trigger.

```
T1S bus --(tap stub)--> pmod/ (RS-485 receiver) --> JA1 --> dme_rx --> t1s_pcs_rx --> events --+--> trigger pulses (JA2..JA7)
                                                                        plca_track -------------+--> LEDs, 7-segment counters
```

The decoder works from the raw line signal, not from a PHY, so it sees
everything including beacons and commits, which a PHY's MII hides.

## Hardware

- Basys 3 (Artix-7 XC7A35T, 100 MHz oscillator).
- The tap Pmod in [`pmod/`](pmod/README.md) on connector **JA**. It is an
  RS-485 receiver (SN65HVD78) used as a high-impedance differential-to-logic
  converter: 10BASE-T1S drives about ±1 V differential, well above the
  receiver's ±200 mV thresholds, and its fail-safe output idles high during
  bus silence so there is no chatter. Keep the stub from the bus to the Pmod
  short (a few cm) and do not close the termination jumper unless the Pmod is
  the physical end of the bus.
- Trigger outputs are 3.3 V logic pulses on the Pmod's SMA (TRIG0) and pin
  header (TRIG0..3).

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
| JA1  | RX       | input from the tap receiver                               |
| JA2  | TRIG0    | switch-selected trigger (SMA on the Pmod)                 |
| JA3  | TRIG1    | BEACON, 100 ns                                            |
| JA4  | TRIG2    | SSD (packet start), 100 ns                                |
| JA7  | TRIG3    | any error (ESDERR, ESDJAB, CRC, protocol, runt), 100 ns   |
| JA8  | DE       | RS-485 driver enable, held low                            |
| JA9  | TXD      | RS-485 driver data, unused                                |
| JA10 | CARRIER  | level: transitions present on the line (not SILENCE)      |

Seven-segment display: BTNU/BTND cycle the mode, the lit decimal point shows
which (rightmost = mode 0). BTNC clears the error counters.

| Mode | Shows (hex)                         |
|------|-------------------------------------|
| 0    | good packets per second             |
| 1    | beacons per second                  |
| 2    | CRC errors since reset              |
| 3    | protocol errors + runts since reset |

## Trigger timing

Events are recognised when the symbol that defines them is complete, so the
pulse comes a fixed delay after the event on the wire: about 0.45 µs after the
first edge of a beacon (one 5B symbol plus pipeline), about 30 ns after the
last edge of an SSD, SFD or ESD symbol. CRC errors are known at ESDOK, i.e. at
the end of the packet. Transmissions ending in a 0 bit are only complete
once the line goes silent, which adds 140 ns for those. The delay is constant,
so set the scope's trigger delay once.

## How it decodes

- `rtl/dme_rx.vhd`: samples the line at 100 MHz and measures the time between
  edges. Every 80 ns bit cell starts with a transition; a 1 has another one
  40 ns later. The first edge after SILENCE (160 ns without edges) is a symbol
  boundary.
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

Constants (symbol codes, timings, PLCA defaults) are in `rtl/t1s_pkg.vhd`
with their sources. The ESDJAB symbol value is the one thing not confirmed
from public documents; a wrong guess only moves jabber from the ESDJAB
event to the protocol-error event.

Known limits: node IDs assume the default `to_timer` of 32 bit times and a
node that pauses within a burst for longer than 160 ns is counted as the next
ID; on a CSMA/CD (non-PLCA) segment node IDs are meaningless (LED10 off).
Data-dependent triggers (addresses, payload patterns) are not implemented.

## Build and test

```sh
cd t1s_trigger
./go.sh                                   # Vivado: synth, place, route, bitstream, program over JTAG
CI=1 ./go.sh                              # build only
docker run --rm -v "$PWD/..":/src -w /src/t1s_trigger hdlc/ghdl:yosys sim/run.sh   # testbench
```

`sim/tb_top.vhd` contains a behavioural 10BASE-T1S transmitter (DME, 4B/5B,
scrambler, FCS) and exercises beacons, transmit-opportunity counting, commit,
good/bad FCS, ESDERR, ESDJAB, bursts, runts, invalid symbols, truncated
transmissions, DME violations, heartbeat and the switch gating and pulse
widths. It is run by `ci/check.sh`; the Vivado workflow builds the bitstream.

## Sources

- IEEE 802.3cg Clause 147 drafts on ieee802.org (comment resolution r2.0,
  Sept 2018; D0.3, Nov 2017): 4B/5B table, DME rules, scrambler, PCS state
  machines, PLCA timers.
- OPEN Alliance 10BASE-T1S PCS compliance test suite v1.0 and TC14/TC10
  sleep/wake specification 1.0: final symbol names (SSD = H, ESDOK/ESDBRS = R,
  ESD/HB/SUSPEND = T), packet structure, nine-symbol descrambler lock.
- Microchip LAN867x datasheet: PMA transmitter 0.8–1.2 V differential,
  receiver input impedance and capacitance.
