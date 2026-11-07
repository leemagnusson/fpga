#!/usr/bin/env python3
"""Swept-sine input impedance of the T1S line as seen from the generator end.

Two ways: with only the launch-point channel, |Z| = Rs*r/(1-r) from the assumed
open-circuit voltage (magnitude only). With --gen-chan N (a scope channel on the
generator side of the series resistor, e.g. a BNC T at the scope input with the
coax passing through) the line current is (Vg - Vl)/Rser from the two complex
amplitudes of the same acquisition, so Z = Vl/I comes out with phase and no
assumption about the generator. --end-chan M adds the transfer Vend/Vl of the
line. The coax between the T and the series resistor must be short compared
with a wavelength (a few cm per 10 MHz of top frequency) for Vg to be the
voltage at the resistor.

The generator (50 Ohm inside + 50 Ohm series = 100 Ohm source, open-circuit 2 Vpp
for the 1 Vpp setting) drives a sine at each frequency; the probe at the launch
point measures the line voltage V. The divider gives the apparent input impedance
|Z| = Rs * r / (1 - r) with r = V / Voc (magnitude only, no phase reference), so
a matched 100 Ohm line reads flat at 100; an open stub or a reflection shows up as
ripple with a period of c_cable / (2 L).

Generator and scope settings are restored afterwards (the arb file is re-opened).

usage: mxo_fra.py [-d /dev/usbtmc4] [-o arb/fra.csv] [--svg arb/fra.svg] [--rs 100] [--voc 2]
                  [--fmin 1e5] [--fmax 1e8] [--points 41]
"""
import argparse
import cmath
import csv
import math
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mxo_arb import Usbtmc, reopen   # noqa: E402
from mxo_capture import read_block   # noqa: E402


def lockin(v, t0, dt, f):
    """Complex amplitude of the fundamental at f (least-squares sine fit), volts 0-peak,
    phase referred to t = 0 of the acquisition so channels of one capture are comparable."""
    n = len(v)
    m = sum(v) / n
    w = 2 * math.pi * f
    c = s = 0.0
    for i, x in enumerate(v):
        a = w * (t0 + i * dt)
        c += (x - m) * math.cos(a)
        s += (x - m) * math.sin(a)
    return complex(2 * c / n, -2 * s / n)


def lockin_amplitude(v, t0, dt, f):
    return abs(lockin(v, t0, dt, f))


def read_channel(dev, ch):
    hdr = dev.ask(f'{ch}:DATA:HEAD?').split(',')
    xstart, xstop = float(hdr[0]), float(hdr[1])
    dev.write(f'{ch}:DATA?')
    raw = read_block(dev)
    v = struct.unpack(f'<{len(raw) // 4}f', raw[:len(raw) // 4 * 4])
    dt = (xstop - xstart) / max(1, len(v) - 1)
    return v, xstart, dt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-d', '--dev', default='/dev/usbtmc4')
    ap.add_argument('-c', '--chan', type=int, default=1)
    ap.add_argument('-g', '--gen', type=int, default=1)
    ap.add_argument('-o', '--out', default='arb/fra.csv')
    ap.add_argument('--svg')
    ap.add_argument('--rs', type=float, default=100, help='total source resistance, ohms')
    ap.add_argument('--voc', type=float, default=2.0, help='generator open-circuit Vpp at the chosen level')
    ap.add_argument('--level', type=float, default=1.0, help='generator VOLT setting (Vpp, 50 ohm convention)')
    ap.add_argument('--fmin', type=float, default=1e5)
    ap.add_argument('--fmax', type=float, default=1e8)
    ap.add_argument('--points', type=int, default=41)
    ap.add_argument('--cycles', type=int, default=20)
    ap.add_argument('--linear', action='store_true', help='linear frequency steps instead of log')
    ap.add_argument('--gen-chan', type=int, default=0,
                    help='scope channel on the generator side of the series resistor (T at the scope input); '
                         'with it, Z = Rser * Vl / (Vg - Vl) from the two complex amplitudes, no Voc assumption')
    ap.add_argument('--rser', type=float, default=50, help='series resistor between the generator coax and the line')
    ap.add_argument('--end-chan', type=int, default=0, help='scope channel at the far end of the line (transfer Vend/Vl)')
    a = ap.parse_args()
    wg = f'WGEN{a.gen}'
    ch = f'CHAN{a.chan}'
    dev = Usbtmc(a.dev)
    dev.write('*CLS')
    saved = {k: dev.ask(k + '?').strip() for k in ('TIM:RANG', 'TRIG:MODE', f'{wg}:VOLT', f'{wg}:FUNC')}
    print('saved:', saved)
    dev.write('FORM REAL,32'); dev.write('FORM:BORD LSBF')
    dev.write('TRIG:MODE AUTO')
    dev.write(f'{wg}:FUNC SIN')
    dev.write(f'{wg}:VOLT:OFFS 0')
    dev.write(f'{wg}:VOLT {a.level}')
    dev.write(f'{wg}:ENAB 1')
    rows = []
    for i in range(a.points):
        f = a.fmin + (a.fmax - a.fmin) * i / (a.points - 1) if a.linear else a.fmin * (a.fmax / a.fmin) ** (i / (a.points - 1))
        dev.write(f'{wg}:FREQ {f:.6g}')
        rng = max(a.cycles / f, 200e-9)
        dev.write(f'TIM:RANG {rng:.4g}')
        time.sleep(0.3)
        dev.write('SING')
        dev.ask('*OPC?')
        time.sleep(min(0.5, rng * 2))
        v, xstart, dt = read_channel(dev, ch)
        vl = lockin(v, xstart, dt, f)
        vpp = 2 * abs(vl)
        r = vpp / a.voc
        z = a.rs * r / (1 - r) if r < 0.999 else float('inf')
        row = {'freq_hz': f'{f:.6g}', 'vpp': f'{vpp:.4f}', 'ratio': f'{r:.4f}', 'z_apparent': f'{z:.1f}'}
        line = f'{f / 1e6:9.4f} MHz  Vl {vpp:.3f} Vpp  r {r:.3f}  |Z|voc {z:6.1f}'
        if a.gen_chan:
            vg_s, g0, gdt = read_channel(dev, f'CHAN{a.gen_chan}')
            vg = lockin(vg_s, g0, gdt, f)
            i = (vg - vl) / a.rser
            zc = vl / i if abs(i) > 1e-9 else complex(float('inf'), 0)
            row.update({'vg_vpp': f'{2 * abs(vg):.4f}', 'z_mag': f'{abs(zc):.1f}', 'z_phase_deg': f'{math.degrees(cmath.phase(zc)):.1f}',
                        'z_real': f'{zc.real:.1f}', 'z_imag': f'{zc.imag:.1f}'})
            z = abs(zc)
            row['z_apparent'] = f'{z:.1f}'
            line += f'  Vg {2 * abs(vg):.3f}  Z {abs(zc):6.1f} ohm {math.degrees(cmath.phase(zc)):+6.1f} deg ({zc.real:.0f}{zc.imag:+.0f}j)'
        if a.end_chan:
            ve_s, e0, edt = read_channel(dev, f'CHAN{a.end_chan}')
            ve = lockin(ve_s, e0, edt, f)
            h = ve / vl if abs(vl) > 1e-9 else complex(0, 0)
            row.update({'end_vpp': f'{2 * abs(ve):.4f}', 'h_end_db': f'{20 * math.log10(max(abs(h), 1e-9)):.2f}',
                        'h_end_phase_deg': f'{math.degrees(cmath.phase(h)):.1f}'})
            line += f'  end/launch {20 * math.log10(max(abs(h), 1e-9)):+5.2f} dB {math.degrees(cmath.phase(h)):+6.1f} deg'
        err = dev.err()
        row.update({'samples': len(v), 'err': err if not err.startswith('0,') else ''})
        rows.append(row)
        print(line + (f'  {err}' if not err.startswith('0,') else ''), flush=True)
    # restore
    dev.write(f"TIM:RANG {saved['TIM:RANG']}")
    dev.write(f"TRIG:MODE {saved['TRIG:MODE']}")
    dev.write(f"{wg}:VOLT {saved[wg + ':VOLT']}")
    if saved[wg + ':FUNC'].upper().startswith('ARB'):
        reopen(dev, wg)
    print('restored:', {k: dev.ask(k + '?').strip() for k in ('TIM:RANG', 'TRIG:MODE', f'{wg}:VOLT', f'{wg}:FUNC')})
    with open(a.out, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print('wrote', a.out)
    if a.svg:
        plot(rows, a.svg, a.rs)


def plot(rows, path, rs):
    INK, INK2, MUTED, GRID, AXIS, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
    BLUE = '#2a78d6'
    W, H, L, R, T, B = 760, 420, 70, 30, 44, 50
    fs = [float(r['freq_hz']) for r in rows]
    zs = [min(float(r['z_apparent']), 1e4) for r in rows]
    fmin, fmax = min(fs), max(fs)
    zmin = max(1, min(zs) * 0.7)
    zmax = max(zs) * 1.4
    def X(f): return L + (W - L - R) * math.log10(f / fmin) / math.log10(fmax / fmin)
    def Y(z): return H - B - (H - B - T) * math.log10(max(zmin, min(zmax, z)) / zmin) / math.log10(zmax / zmin)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="{SURF}"/>',
         f'<text x="{L}" y="22" font-size="15" font-weight="600" fill="{INK}">Apparent input impedance of the T1S line from the generator end</text>',
         f'<text x="{L}" y="37" fill="{INK2}" font-size="11">swept sine, {rs:g} ohm source, probe at the launch point; |Z| = Rs·r/(1−r), r = Vline/Voc (magnitude only)</text>']
    for z in (10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 1000):
        if not zmin <= z <= zmax:
            continue
        y = Y(z)
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID if z != 100 else AXIS}"/>')
        o.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}">{z}</text>')
    d = 1
    while d <= fmax:
        for k in (1, 2, 5):
            f = k * d
            if fmin <= f <= fmax:
                x = X(f)
                o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{T}" y2="{H - B}" stroke="{GRID}"/>')
                if k == 1 or f in (2e5, 5e5, 2e6, 5e6, 2e7, 5e7):
                    lab = f'{f / 1e6:g} MHz' if f >= 1e6 else f'{f / 1e3:g} kHz'
                    o.append(f'<text x="{x:.1f}" y="{H - B + 16}" text-anchor="middle" fill="{MUTED}">{lab}</text>')
        d *= 10
    o.append(f'<text transform="translate(16,{(T + H - B) / 2:.0f}) rotate(-90)" text-anchor="middle" fill="{INK2}">|Z| apparent, ohm (log)</text>')
    o.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 14}" text-anchor="middle" fill="{INK2}">frequency (log)</text>')
    pts = ' '.join(f'{X(f):.1f},{Y(z):.1f}' for f, z in zip(fs, zs))
    o.append(f'<polyline points="{pts}" fill="none" stroke="{BLUE}" stroke-width="2" stroke-linejoin="round"/>')
    for f, z in zip(fs, zs):
        o.append(f'<circle cx="{X(f):.1f}" cy="{Y(z):.1f}" r="3" fill="{BLUE}" stroke="{SURF}" stroke-width="1.5"/>')
    o.append('</svg>')
    open(path, 'w').write('\n'.join(o))
    print('wrote', path)


if __name__ == '__main__':
    main()
