#!/usr/bin/env python3
"""Fit the path from generator to probe as gain x second-order low-pass (f0, Q) by
comparing a capture (mxo_capture.py) with the ideal waveform (t1s_arb.py -F plain
at --ideal-rate). Grid search, pure Python, 1 ns working grid.

usage: t1s_channel_fit.py capture.f32 ideal_plain.csv [--ideal-rate 1e9]
"""
import argparse
import math
import struct


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('capture'); ap.add_argument('ideal'); ap.add_argument('--ideal-rate', type=float, default=1e9)
    a = ap.parse_args()
    raw = open(a.capture, 'rb').read()
    v = struct.unpack('<%df' % (len(raw) // 4), raw)
    x0, x1, n = open(a.capture + '.hdr').read().split()[:3]
    x0, n = float(x0), int(n); dt = (float(x1) - x0) / (n - 1)
    step = max(1, round(1e-9 / dt))                   # 1 ns grid
    meas = v[::step]
    ideal = [float(x) for x in open(a.ideal) if x.strip() and not x.startswith('Rate')]
    # align: first threshold crossing in each
    im = next(i for i, x in enumerate(meas) if abs(x) > 0.18)
    ii = next(i for i, x in enumerate(ideal) if abs(x) > 0.18)
    L = min(len(ideal) - ii, len(meas) - im) - 3000
    m = meas[im - 200:im - 200 + L]; u = ideal[ii - 200:ii - 200 + L]
    Ts = 1e-9

    def biquad(x, f0, q):
        w0 = 2 * math.pi * f0 * Ts; al = math.sin(w0) / (2 * q); cw = math.cos(w0)
        b0 = (1 - cw) / 2; b1 = 1 - cw; b2 = b0; a0 = 1 + al; a1 = -2 * cw; a2 = 1 - al
        b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
        y = [0.0] * len(x); x1 = x2 = y1 = y2 = 0.0
        for i, xi in enumerate(x):
            yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2, x1, y2, y1 = x1, xi, y1, yi; y[i] = yi
        return y

    def cost(f0, q, delay):
        y = biquad(u, f0, q)
        # best gain by least squares, allowing an integer delay (ns)
        num = den = 0.0
        for i in range(delay, L):
            num += y[i - delay] * m[i]; den += y[i - delay] * y[i - delay]
        g = num / den if den else 1
        e = sum((g * y[i - delay] - m[i]) ** 2 for i in range(delay, L, 4))
        return e, g

    best = None
    for f0 in (8e6, 10e6, 12e6, 14e6, 16e6, 18e6, 20e6, 24e6, 28e6, 34e6):
        for q in (0.7, 1.0, 1.4, 2.0, 2.8, 4.0):
            for d in (0, 10, 20, 30, 40):
                e, g = cost(f0, q, d)
                if best is None or e < best[0]:
                    best = (e, f0, q, d, g)
    e, f0, q, d, g = best
    # refine around the best
    for f in (f0 * 0.85, f0 * 0.92, f0, f0 * 1.08, f0 * 1.15):
        for qq in (q * 0.8, q * 0.9, q, q * 1.1, q * 1.25):
            for dd in range(max(0, d - 8), d + 9, 4):
                ee, gg = cost(f, qq, dd)
                if ee < e:
                    e, f0, q, d, g = ee, f, qq, dd, gg
    y = biquad(u, f0, q)
    resid = math.sqrt(sum((g * y[i - d] - m[i]) ** 2 for i in range(d, L)) / (L - d))
    raw_err = math.sqrt(sum((u[i] - m[i]) ** 2 for i in range(L)) / L)
    print(f'best fit: gain {g:.3f}, f0 {f0 / 1e6:.1f} MHz, Q {q:.2f}, delay {d} ns; '
          f'residual {resid * 1e3:.0f} mV rms (vs {raw_err * 1e3:.0f} mV rms with no model); '
          f'peaking {20 * math.log10(q) if q > 0.707 else 0:.1f} dB, step overshoot '
          f'{100 * math.exp(-math.pi / math.sqrt(4 * q * q - 1)) if q > 0.5 else 0:.0f} %')


if __name__ == '__main__':
    main()
