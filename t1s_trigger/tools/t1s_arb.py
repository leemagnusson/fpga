#!/usr/bin/env python3
"""Turn an Ethernet frame into a 10BASE-T1S line waveform for an arbitrary
waveform generator: SYNC SYNC SSD SSD, scrambled preamble and SFD, scrambled
data, FCS (correct or deliberately wrong) and the end delimiter, DME encoded
at 12.5 MBd with silence before and after. Same transmitter model as
sim/tb_top.vhd.

The frame is given as the bytes after the preamble/SFD and before the FCS,
i.e. destination MAC first, as hex (spaces, colons and tcpdump-style
"0x0010:" offsets are ignored). Frames shorter than 60 bytes are zero
padded unless --no-pad.

usage:
  t1s_arb.py -o good.csv --dst 02:00:04:00:00:03 --src 9c:95:6e:b5:60:e5 --type 88b5 \\
             --payload "0000 0000 0000 0203 0006 7365 7269 616c ..."
  t1s_arb.py -o bad.csv --bad-crc --frame "0200 0400 0003 9c95 6eb5 60e5 88b5 ..."

Output formats (-F):
  plain   one voltage per line, no header             (HMExplorer arbitrary import, most tools)
  time    "time_s,voltage" per line                     (CSV importers that want an x column)
  rs      R&S WaveGen CSV: "Rate = <Sa/s>" line, then "time,voltage" (MXO, RTx)
  rsv     the same with voltage only (a third of the size, for long frames)

The waveform is single ended: +A while the line is positive, -A while
negative, 0 at silence. For a 1 Vpp differential bus level use -a 0.5 and set
the generator for a 50 ohm load. --check decodes the generated bit stream and
reports the symbols and FCS result so you know what the file contains.
"""
import argparse
import math
import random
import re
import sys

# 4B/5B (IEEE 802.3 Table 147-1), 5B codes written MSB..LSB; sent LSB first
ENC = ['11110', '01001', '10100', '10101', '01010', '01011', '01110', '01111',
       '10010', '10011', '10110', '10111', '11010', '11011', '11100', '11101']
SYM = {'J': '11000', 'H': '00100', 'T': '01101', 'R': '00111', 'K': '10001',
       'N': '01000', 'S': '11001', 'I': '11111'}
DEC = {code: f'{i:X}' for i, code in enumerate(ENC)}
DEC.update({code: name for name, code in SYM.items()})
BAD_CODE = '00001'                      # not in Table 147-1: an invalid code group
SCR_SEED = '10101100111000101'           # scrambler start state used by tb_top (any non-zero value works)
CRC_RESIDUE = 0xDEBB20E3


def parse_hex(s):
    s = re.sub(r'0x[0-9a-fA-F]+:', ' ', s)              # tcpdump offsets
    s = re.sub(r'[^0-9a-fA-F]', '', s)
    if len(s) % 2:
        sys.exit('odd number of hex digits')
    return bytes.fromhex(s)


def crc32_update(crc, nib):
    """Reflected Ethernet CRC-32 over one nibble, LSB first (as t1s_pkg)."""
    for i in range(4):
        fb = (crc ^ (nib >> i)) & 1
        crc = (crc >> 1) ^ (0xEDB88320 if fb else 0)
    return crc


class Tx:
    """Builds the list of line levels, one per half bit cell (+1 / -1 / 0)."""

    def __init__(self):
        self.half = []                  # levels, one per 40 ns
        self.pol = -1
        self.scr = [int(c) for c in SCR_SEED]     # scr[0] = bit 16 ... scr[16] = bit 0 (VHDL 16 downto 0)
        self.symbols = []

    def _toggle(self):
        self.pol = -self.pol

    def sym(self, code):                # code: 5 chars MSB..LSB
        self.symbols.append(DEC.get(code, '?'))
        for i in range(5):
            bit = code[4 - i]           # LSB first
            self._toggle(); self.half.append(self.pol)
            if bit == '1':
                self._toggle()
            self.half.append(self.pol)

    def nibble(self, n):                # scramble LSB first, then 4B/5B
        sd = 0
        for i in range(4):
            b = ((n >> i) & 1) ^ self.scr[16 - 13] ^ self.scr[16 - 16]
            self.scr = self.scr[1:] + [b]
            sd |= b << i
        self.sym(ENC[sd])

    def byte(self, b):
        self.nibble(b & 0xF)
        self.nibble(b >> 4)

    def silence(self, half_cells):
        self.half += [0] * half_cells

    def nibble_bad(self, n):            # run the scrambler as for n, but send an invalid 5B code
        for i in range(4):
            b = ((n >> i) & 1) ^ self.scr[16 - 13] ^ self.scr[16 - 16]
            self.scr = self.scr[1:] + [b]
        self.sym(BAD_CODE)

    def packet(self, frame, bad_crc, end='TR', bad_symbol=None, extra_nibble=False, close=True):
        for c in 'JJHH':
            self.sym(SYM[c])
        for _ in range(11):
            self.nibble(0x5)
        self.nibble(0xD)
        crc = 0xFFFFFFFF
        for k, b in enumerate(frame):
            for j, nib in enumerate((b & 0xF, b >> 4)):
                if bad_symbol is not None and 2 * k + j == bad_symbol:
                    self.nibble_bad(nib)
                else:
                    self.nibble(nib)
            crc = crc32_update(crc, b & 0xF)
            crc = crc32_update(crc, b >> 4)
        fcs = crc ^ 0xFFFFFFFF
        if bad_crc is not None:
            fcs ^= 1 << bad_crc
        for i in range(4):
            self.byte((fcs >> (8 * i)) & 0xFF)
        if extra_nibble:
            self.nibble(0xA)            # one nibble too many: not an integral number of octets
        for c in end:
            self.sym(SYM[c])
        if close:                       # closing cell-boundary transition after the last bit,
            self._toggle()              # as a real PHY sends (held one half cell, then silence)
            self.half.append(self.pol)
        return fcs


def check(half):
    """Decode the half-cell levels back (DME, 4B/5B, descrambler, CRC) and describe them."""
    # edges between consecutive half cells; DME: a toggle at every cell start, plus one mid-cell for a 1
    bits = []
    i = 0
    # skip leading silence
    while i < len(half) and half[i] == 0:
        i += 1
    prev = 0
    while i + 1 < len(half) and half[i] != 0 and half[i + 1] != 0:   # a lone half cell before silence is the closing edge
        if half[i] == prev:
            return 'DME violation: no transition at a cell start'
        bits.append(1 if half[i + 1] != half[i] else 0)
        prev = half[i + 1]
        i += 2
    syms = []
    for k in range(0, len(bits) - len(bits) % 5, 5):
        code = ''.join(str(b) for b in bits[k:k + 5][::-1])     # back to MSB..LSB
        syms.append(DEC.get(code, '?' + code))
    out = ['symbols: ' + ' '.join(syms[:4]) + ' |' + ''.join(syms[4:16]) + '| ... ' + ' '.join(syms[-2:]),
           f'{len(syms)} symbols, {len(bits)} bits, {len(bits) * 80 / 1000:.2f} us on the wire']
    # descramble the data part and check the FCS residue
    scr = [0] * 17
    crc = 0xFFFFFFFF
    data = []
    for k in range(4, len(syms) - 2):
        if len(syms[k]) != 1 or syms[k] not in '0123456789ABCDEF':
            out.append(f'data symbol {k - 4}: {syms[k]} is not a data code (RX_ER at a PHY)')
            sd = 0
        else:
            sd = ENC.index(DEC_INV[syms[k]])
        n = 0
        for b in range(4):
            x = (sd >> b) & 1
            n |= (x ^ scr[16 - 13] ^ scr[16 - 16]) << b
            scr = scr[1:] + [x]
        data.append(n)
    # first 12 nibbles are preamble/SFD; descrambler needs 9 nibbles to lock so only check the tail
    pre = ''.join(f'{n:X}' for n in data[:12])
    out.append(f'preamble/SFD nibbles after descrambling: {pre} (last three should be 55D)')
    for n in data[12:]:
        crc = crc32_update(crc, n)
    octets = len(data[12:]) // 2
    out.append(f'{octets} octets incl. FCS; CRC register 0x{crc:08X} -> '
               + ('FCS GOOD' if crc == CRC_RESIDUE else 'FCS BAD (residue 0x%08X expected)' % CRC_RESIDUE))
    return '\n'.join(out)


DEC_INV = {v: k for k, v in DEC.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--frame', help='whole frame as hex, dst MAC first, no FCS')
    ap.add_argument('--dst'); ap.add_argument('--src'); ap.add_argument('--type', dest='etype')
    ap.add_argument('--payload', help='bytes after the EtherType, as hex')
    ap.add_argument('--bad-crc', nargs='?', const=5, type=int, default=None, metavar='BIT',
                    help='corrupt the FCS by flipping one bit (0..31, default 5)')
    ap.add_argument('--no-pad', action='store_true', help="don't pad the frame to 60 bytes")
    ap.add_argument('--end', default='TR', help='end delimiter symbols: TR (normal), TK (ESDERR), TS (ESDJAB)')
    ap.add_argument('--odd-nibble', action='store_true',
                    help='send one extra data nibble after the FCS (alignment error: frame is not whole octets)')
    ap.add_argument('--bad-symbol', type=int, metavar='N',
                    help='replace data nibble N (0 = first byte, low nibble) with an invalid 5B code')
    ap.add_argument('-r', '--sample-rate', type=float, default=250e6, help='samples per second (default 250 MSa/s)')
    ap.add_argument('-a', '--amplitude', type=float, default=0.5, help='volts, line level (+a / -a / 0)')
    ap.add_argument('-e', '--edge', type=float, default=10e-9, help='edge time in seconds, linear ramp (0 = ideal)')
    ap.add_argument('--noise', type=float, default=0.0, help='Gaussian noise added to every sample, V rms')
    ap.add_argument('--jitter', type=float, default=0.0, help='Gaussian timing jitter on every transition, s rms')
    ap.add_argument('--jitter-dist', choices=['gauss', 'uniform'], default='gauss',
                    help='distribution of the random jitter (uniform = bounded, same rms)')
    ap.add_argument('--dcd', type=float, default=0.0, metavar='S',
                    help='duty-cycle distortion: positive half cells longer by this, negative shorter')
    ap.add_argument('--pj', type=float, nargs=2, metavar=('HZ', 'SPEAK'),
                    help='periodic jitter: every edge moved by SPEAK*sin(2*pi*HZ*t)')
    ap.add_argument('--ddj', type=float, default=0.0, metavar='S',
                    help='data dependent jitter: an edge that follows a full 80 ns cell arrives this much late')
    ap.add_argument('--ring', type=float, nargs=3, metavar=('HZ', 'FRAC', 'TAU'),
                    help='ringing after each edge: FRAC of the step swing at HZ, decaying with time constant TAU s')
    ap.add_argument('--offset', type=float, default=0.0, help='DC offset added to the whole waveform, V')
    ap.add_argument('--lowpass', type=float, default=0.0, metavar='TAU',
                    help='single-pole low-pass on the whole waveform, time constant s (cable loss, ISI)')
    ap.add_argument('--tone', type=float, nargs=2, metavar=('HZ', 'VPEAK'),
                    help='add a sine of this frequency and peak amplitude (closes the eye vertically)')
    ap.add_argument('--seed', type=int, default=1, help='random seed for noise and jitter')
    ap.add_argument('--no-close', action='store_true',
                    help='omit the closing transition after the ESD (the pre-2026-11-04 behaviour; '
                         'a LAN8670 then mangles the frame end on some shots)')
    ap.add_argument('--lead', type=float, default=2e-6, help='silence before the packet, seconds')
    ap.add_argument('--trail', type=float, default=2e-6, help='silence after the packet, seconds')
    ap.add_argument('-F', '--format', choices=['plain', 'time', 'rs', 'rsv'], default='plain')
    ap.add_argument('--check', action='store_true', help='decode the result and print what it contains')
    a = ap.parse_args()

    if a.frame:
        frame = parse_hex(a.frame)
    elif a.dst and a.src and a.etype and a.payload is not None:
        frame = parse_hex(a.dst) + parse_hex(a.src) + parse_hex(a.etype) + parse_hex(a.payload)
        if len(parse_hex(a.dst)) != 6 or len(parse_hex(a.src)) != 6 or len(parse_hex(a.etype)) != 2:
            sys.exit('dst/src must be 6 bytes, type 2 bytes')
    else:
        sys.exit('give --frame, or --dst --src --type --payload')
    if len(frame) < 60 and not a.no_pad:
        frame = frame + bytes(60 - len(frame))

    tx = Tx()
    half_per_s = 25e6
    tx.silence(round(a.lead * half_per_s))
    fcs = tx.packet(frame, a.bad_crc, a.end.upper(), a.bad_symbol, a.odd_nibble, not a.no_close)
    tx.silence(round(a.trail * half_per_s))

    # half cells -> transitions (time, new level), each transition optionally moved by
    # Gaussian jitter, then samples with a linear ramp of a.edge centred on each transition
    rng = random.Random(a.seed)
    half_t = 1 / half_per_s
    trans = []                                  # (time, level after it)
    last_edge = None
    for i in range(1, len(tx.half)):
        if tx.half[i] != tx.half[i - 1]:
            t = i * half_t
            if a.jitter:                            # random jitter
                if a.jitter_dist == 'uniform':      # bounded, same rms as the Gaussian
                    t += rng.uniform(-a.jitter * math.sqrt(3), a.jitter * math.sqrt(3))
                else:
                    t += rng.gauss(0, a.jitter)
            if a.dcd:                               # duty-cycle distortion: positive half cells longer
                t += a.dcd / 2 if tx.half[i] < 0 else -a.dcd / 2
            if a.pj:                                # periodic (sinusoidal) jitter
                t += a.pj[1] * math.sin(2 * math.pi * a.pj[0] * i * half_t)
            if a.ddj and last_edge is not None:     # data dependent: edge after a full cell comes late
                if i * half_t - last_edge > 1.5 * half_t:
                    t += a.ddj
            last_edge = i * half_t
            trans.append((t, tx.half[i]))
    trans.sort()
    n = round(len(tx.half) * half_t * a.sample_rate)
    samples = []
    j = 0
    level = tx.half[0]
    for k in range(n):
        t = k / a.sample_rate
        while j < len(trans) and trans[j][0] <= t:
            level = trans[j][1]
            j += 1
        v = level
        if a.edge > 0:
            # inside the ramp around the previous or the next transition?
            if j > 0 and t - trans[j - 1][0] < a.edge / 2:
                t0, v1 = trans[j - 1]
                v0 = trans[j - 2][1] if j > 1 else tx.half[0]
                v = v0 + (v1 - v0) * (t - t0 + a.edge / 2) / a.edge
            elif j < len(trans) and trans[j][0] - t < a.edge / 2:
                t1, v1 = trans[j]
                v = level + (v1 - level) * (t - t1 + a.edge / 2) / a.edge
        v *= a.amplitude
        if a.ring and j > 0:                    # damped ringing after every transition, in its direction
            t0, v1 = trans[j - 1]
            v0 = trans[j - 2][1] if j > 1 else tx.half[0]
            dt = t - t0
            if 0 <= dt < 8 * a.ring[2]:
                v += (v1 - v0) * a.amplitude * a.ring[1] * math.sin(2 * math.pi * a.ring[0] * dt) * math.exp(-dt / a.ring[2])
        if a.noise:
            v += rng.gauss(0, a.noise)
        if a.tone:
            v += a.tone[1] * math.sin(2 * math.pi * a.tone[0] * t)
        v += a.offset
        samples.append(v)
    if a.lowpass:                               # single pole RC on the whole waveform (cable-like)
        y = 0.0
        k = (1 / a.sample_rate) / a.lowpass
        for i2, x in enumerate(samples):
            y += (x - y) * k
            samples[i2] = y

    with open(a.out, 'w') as f:
        if a.format in ('rs', 'rsv'):   # R&S WaveGen CSV (MXO/RTx user manual, "Arbitrary waveform files")
            f.write(f'Rate = {a.sample_rate:.0f}\n')
        for k, v in enumerate(samples):
            if a.format in ('plain', 'rsv'):
                f.write(f'{v:.4f}\n')
            else:
                f.write(f'{k / a.sample_rate:.10g},{v:.4f}\n')

    print(f'{a.out}: {len(samples)} samples at {a.sample_rate / 1e6:g} MSa/s = {len(samples) / a.sample_rate * 1e6:.2f} us, '
          f'{len(frame)} byte frame, FCS 0x{fcs:08X}{" (bit %d flipped)" % a.bad_crc if a.bad_crc is not None else ""}{", invalid code at nibble %d" % a.bad_symbol if a.bad_symbol is not None else ""}{", extra nibble" if a.odd_nibble else ""}, end {a.end.upper()}, '
          f'levels +/-{a.amplitude} V'
          + (f', noise {a.noise * 1e3:g} mVrms' if a.noise else '') + (f', jitter {a.jitter * 1e9:g} ns rms' if a.jitter else '')
          + (f', tone {a.tone[0] / 1e6:g} MHz {a.tone[1] * 1e3:g} mVpk' if a.tone else ''))
    if a.check:
        print(check(tx.half))


if __name__ == '__main__':
    main()
