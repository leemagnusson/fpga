#!/usr/bin/env python3
"""Eye diagram of a captured 10BASE-T1S frame (mxo_capture.py .f32 + .f32.hdr).

Recovers the DME half-cell grid (20 ns) from the detected transitions, works out
which half-cell phase is the cell boundary (the one that always has a transition),
folds the whole frame onto a two-cell (80 ns) window and renders a log-density
eye as PNG. Prints jitter of the boundary and mid-cell transitions against the
fitted grid, eye height at the quarter-cell points, and the eye width.

usage: t1s_eye.py capture.f32 [-o eye.png] [--thr 0.18]
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from t1s_analyze import load_f32, transitions  # noqa: E402

HALF = 40e-9                                   # DME half cell: 12.5 MBd, 80 ns cells


def fit_grid(times):
    """Return (phase, half-cell period) of the 20 ns grid by iterative least squares."""
    period = HALF
    # phase: circular mean of t mod period
    ang = [2 * math.pi * (t % period) / period for t in times]
    phase = period * math.atan2(sum(math.sin(x) for x in ang), sum(math.cos(x) for x in ang)) / (2 * math.pi)
    for _ in range(3):
        ks = [round((t - phase) / period) for t in times]
        n = len(times)
        mk, mt = sum(ks) / n, sum(times) / n
        sxx = sum((k - mk) ** 2 for k in ks)
        period = sum((k - mk) * (t - mt) for k, t in zip(ks, times)) / sxx
        phase = mt - period * mk
    return phase, period


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('capture')
    ap.add_argument('-o', '--out')
    ap.add_argument('--thr', type=float, default=0.18)
    ap.add_argument('--width', type=int, default=900)
    ap.add_argument('--height', type=int, default=450)
    a = ap.parse_args()
    v, t0, dt = load_f32(a.capture)
    tr = transitions(v, t0, dt, a.thr)
    edges = [t for t, s in tr if s != 0]
    if len(edges) < 20:
        sys.exit(f'only {len(edges)} transitions found')
    t_first, t_last = edges[0], edges[-1]
    phase, period = fit_grid(edges[1:-1])          # the first and last edge are special (preamble start, closing edge)
    ks = [round((t - phase) / period) for t in edges[1:-1]]
    even = sum(1 for k in ks if k % 2 == 0)
    odd = len(ks) - even
    kmin, kmax = min(ks), max(ks)
    n_cells = (kmax - kmin) // 2 + 1
    # the boundary parity is the one with (close to) one transition per cell
    bparity = 0 if even >= odd else 1
    tie_b = [t - (phase + k * period) for t, k in zip(edges[1:-1], ks) if k % 2 == bparity]
    tie_m = [t - (phase + k * period) for t, k in zip(edges[1:-1], ks) if k % 2 != bparity]
    def rms(x): return math.sqrt(sum(y * y for y in x) / len(x)) if x else float('nan')
    def mean(x): return sum(x) / len(x) if x else float('nan')
    def std(x): return math.sqrt(sum((y - mean(x)) ** 2 for y in x) / len(x)) if x else float('nan')
    def pkpk(x): return (max(x) - min(x)) if x else float('nan')
    cell = 2 * period
    bphase = phase + bparity * period               # time of a cell boundary

    # fold: x = (t - bphase) mod cell, shown over two cells
    W, H = a.width, a.height
    vmax = max(abs(min(v)), abs(max(v))) * 1.05
    span = 2 * cell
    hist = [[0] * W for _ in range(H)]
    i0 = max(0, int((t_first - t0) / dt))
    i1 = min(len(v) - 1, int((t_last - t0) / dt))
    def px(t, y):
        x = ((t - bphase) % cell) / span * W
        return x, (vmax - y) / (2 * vmax) * H
    prev = None
    for i in range(i0, i1 + 1):
        t = t0 + i * dt
        x, y = px(t, v[i])
        for xo in (0, W / 2):                      # draw each sample in both cells of the window
            xx = x + xo
            if prev is not None and abs(xx - prev[0]) < W / 4:
                # short line segment to the previous sample
                n = int(max(abs(xx - prev[0]), abs(y - prev[1]))) + 1
                for s in range(n + 1):
                    xi = int(prev[0] + (xx - prev[0]) * s / n)
                    yi = int(prev[1] + (y - prev[1]) * s / n)
                    if 0 <= xi < W and 0 <= yi < H:
                        hist[yi][xi] += 1
            else:
                xi, yi = int(xx), int(y)
                if 0 <= xi < W and 0 <= yi < H:
                    hist[yi][xi] += 1
            prev = (xx, y)
        prev = (x, y)

    # eye height at the quarter points (20 ns and 60 ns after the boundary): settled levels
    def samples_at(ph, tol=1e-9):
        hi, lo = [], []
        for i in range(i0, i1 + 1):
            t = t0 + i * dt
            d = ((t - bphase - ph) + cell / 2) % cell - cell / 2
            if abs(d) <= tol:
                (hi if v[i] > 0 else lo).append(v[i])
        return hi, lo
    heights = []
    for ph in (cell / 4, 3 * cell / 4):
        hi, lo = samples_at(ph)
        if hi and lo:
            heights.append((ph, min(hi), max(lo), min(hi) - max(lo)))
    width_half = period - (pkpk(tie_b) + pkpk(tie_m)) / 2

    print(f'{len(edges)} transitions, {n_cells} cells, half cell {period * 1e9:.4f} ns '
          f'(rate {1 / (2 * period) / 1e6:.4f} Mb/s), frame {(t_last - t_first) * 1e6:.2f} us')
    print(f'boundary transitions: {len(tie_b)} (expected {n_cells}), mid-cell transitions: {len(tie_m)}')
    print(f'timing vs fitted grid  boundary: mean {mean(tie_b) * 1e9:+.2f} ns, {std(tie_b) * 1e9:.3f} ns rms, '
          f'{pkpk(tie_b) * 1e9:.2f} ns pk-pk;  mid-cell: mean {mean(tie_m) * 1e9:+.2f} ns, '
          f'{std(tie_m) * 1e9:.3f} ns rms, {pkpk(tie_m) * 1e9:.2f} ns pk-pk')
    for ph, hi, lo, h in heights:
        print(f'eye at {ph * 1e9:.0f} ns: upper rail min {hi:+.3f} V, lower rail max {lo:+.3f} V, height {h:.3f} V')
    print(f'eye width (half cell minus pk-pk crossing spread): {width_half * 1e9:.1f} ns of {period * 1e9:.0f}')

    if a.out:
        from PIL import Image
        img = Image.new('RGB', (W, H), (252, 252, 251))
        pix = img.load()
        mx = math.log1p(max(max(r) for r in hist))
        for yi in range(H):
            for xi in range(W):
                c = hist[yi][xi]
                if c:
                    f = math.log1p(c) / mx
                    # light blue -> dark blue -> near black
                    r = int(200 - 190 * f); g = int(220 - 190 * f); b = int(245 - 120 * f)
                    pix[xi, yi] = (r, g, b)
        # grid: 0 V and the cell boundaries / quarter points
        for xi in range(W):
            pix[xi, H // 2] = (160, 160, 160)
        for k in range(0, 9):
            xi = int(k * W / 8)
            if xi < W:
                for yi in range(0, H, 3 if k % 2 else 1):
                    pix[xi, yi] = (120, 120, 120) if k % 2 == 0 else (190, 190, 190)
        img.save(a.out)
        print(f'wrote {a.out}: {span * 1e9:.0f} ns window (cell boundaries at 0, 80, 160 ns; mid-cell at 40, 120), +/-{vmax:.2f} V')


if __name__ == '__main__':
    main()
