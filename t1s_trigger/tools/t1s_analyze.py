#!/usr/bin/env python3
"""Analyse a scope capture of one injected 10BASE-T1S frame (tools/mxo_capture.py
output) against the ideal waveform the generator was asked for.

usage: t1s_analyze.py capture.f32 ideal_plain.csv [--ideal-rate 1e9] [--thr 0.18]
                      [--tie out.csv] [--svg out.svg]
Reports levels, overshoot, noise, transition statistics, where the measured
transition sequence first departs from the ideal one, and the edge timing error
(TIE) of every matched edge.
"""
import argparse
import math
import struct


def load_f32(path):
    data = open(path, 'rb').read()
    v = list(struct.unpack('<%df' % (len(data) // 4), data))
    x0, x1, n = open(path + '.hdr').read().split()[:3]
    x0, x1, n = float(x0), float(x1), int(n)
    return v, x0, (x1 - x0) / (n - 1)


def transitions(v, t0, dt, thr):
    """Hysteresis detector: states -1/0/+1; returns [(time of nearest 0 V crossing, new state)].
    From 0 the state leaves when |v| > thr; from +-1 it flips when v crosses -+thr."""
    out = []
    st = 0
    for i, x in enumerate(v):
        new = st
        if st == 0 and abs(x) > thr:
            new = 1 if x > 0 else -1
        elif st == 1 and x < -thr:
            new = -1
        elif st == -1 and x > thr:
            new = 1
        if new != st:
            # time: interpolated zero crossing just before i (for full edges) or threshold time
            j = i
            if st != 0:
                while j > 0 and (v[j - 1] > 0) == (x > 0):
                    j -= 1
                a, b = v[j - 1], v[j]
                tc = t0 + dt * (j - 1 + (0 - a) / (b - a)) if b != a else t0 + dt * j
            else:
                tc = t0 + dt * i
            out.append((tc, new))
            st = new
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('capture')
    ap.add_argument('ideal')
    ap.add_argument('--ideal-rate', type=float, default=1e9)
    ap.add_argument('--thr', type=float, default=0.18)
    ap.add_argument('--tie')
    ap.add_argument('--svg')
    a = ap.parse_args()

    v, x0, dt = load_f32(a.capture)
    n = len(v)
    act = [i for i in range(0, n, 10) if abs(v[i]) > 0.1]
    i0, i1 = max(0, act[0] - 50), min(n, act[-1] + 50)
    seg = v[i0:i1]
    t0 = x0 + i0 * dt
    print(f'capture: {n} samples, {dt * 1e9:.3f} ns/sample; active {t0 * 1e6:.2f} .. {(x0 + i1 * dt) * 1e6:.2f} us '
          f'({(i1 - i0) * dt * 1e6:.2f} us)')
    hi = sorted(x for x in seg if x > 0.2); lo = sorted(x for x in seg if x < -0.2)
    print(f'levels: median high {hi[len(hi) // 2]:+.3f} V, median low {lo[len(lo) // 2]:+.3f} V; '
          f'extremes {max(seg):+.3f} / {min(seg):+.3f} V')
    # flat-top noise: samples whose 12 ns neighbourhood stays on one side above 0.25 V
    k = int(6e-9 / dt)
    flat = [seg[i] for i in range(k, len(seg) - k, 3)
            if all(abs(seg[j]) > 0.25 and (seg[j] > 0) == (seg[i] > 0) for j in (i - k, i + k))]
    if flat:
        m_hi = [x for x in flat if x > 0]; m_lo = [x for x in flat if x < 0]
        def rms(xs):
            mu = sum(xs) / len(xs); return math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs)), mu
        print(f'flat-top: high {rms(m_hi)[1]:+.3f} V rms dev {rms(m_hi)[0] * 1e3:.1f} mV, '
              f'low {rms(m_lo)[1]:+.3f} V rms dev {rms(m_lo)[0] * 1e3:.1f} mV')
    # before and after the frame: residual signal
    pre = v[max(0, i0 - int(2e-6 / dt)):i0]; post = v[i1:i1 + int(2e-6 / dt)]
    for name, s in (('2 us before', pre), ('2 us after', post)):
        if s:
            print(f'{name}: min {min(s):+.3f} max {max(s):+.3f} V')
    # 10-90 % edge time of the first ten full edges
    tr = transitions(seg, t0, dt, a.thr)
    edges = []
    vh, vl = hi[len(hi) // 2], lo[len(lo) // 2]          # settled levels, not the overshoot
    a10, a90 = vl + 0.1 * (vh - vl), vl + 0.9 * (vh - vl)
    for tc, st in tr[1:40]:
        i = int((tc - t0) / dt)
        lo_i = hi_i = i                                     # walk out from the zero crossing
        while lo_i > 0 and a10 < seg[lo_i] < a90: lo_i -= 1
        while hi_i < len(seg) - 1 and a10 < seg[hi_i] < a90: hi_i += 1
        edges.append((hi_i - lo_i) * dt)
    if edges:
        edges.sort()
        print(f'10-90 % edge time: median {edges[len(edges) // 2] * 1e9:.1f} ns '
              f'(range {edges[0] * 1e9:.1f} .. {edges[-1] * 1e9:.1f})')
    print(f'transitions at +/-{a.thr} V: {len(tr)}')
    iv = [(tr[i][0] - tr[i - 1][0]) * 1e9 for i in range(1, len(tr))]
    bins = {'<30': 0, '30-50': 0, '50-70': 0, '70-90': 0, '>90': 0}
    for x in iv:
        bins['<30' if x < 30 else '30-50' if x < 50 else '50-70' if x < 70 else '70-90' if x < 90 else '>90'] += 1
    print('interval histogram (ns):', bins)

    # ideal waveform
    iv_ideal = [float(x) for x in open(a.ideal) if x.strip() and not x.startswith('Rate')]
    tri = transitions(iv_ideal, 0.0, 1 / a.ideal_rate, a.thr)
    print(f'ideal transitions: {len(tri)}')
    # align on the first transition, compare interval sequences
    m = min(len(tr), len(tri))
    div = None
    for i in range(1, m):
        d = (tr[i][0] - tr[i - 1][0]) - (tri[i][0] - tri[i - 1][0])
        if abs(d) > 15e-9 or tr[i][1] != tri[i][1]:
            div = i
            break
    first_t = tr[0][0]
    if div is None:
        print(f'transition sequence matches the ideal for all {m} transitions' +
              (f' (measured has {len(tr) - len(tri):+d} extra)' if len(tr) != len(tri) else ''))
    else:
        tm = tr[div][0]
        bit = (tri[div][0] - tri[0][0]) / 80e-9
        print(f'DIVERGES at transition {div} of {m}: measured interval {(tr[div][0] - tr[div - 1][0]) * 1e9:.1f} ns, '
              f'ideal {(tri[div][0] - tri[div - 1][0]) * 1e9:.1f} ns, at t={tm * 1e6:.3f} us, '
              f'{(tm - first_t) * 1e6:.3f} us after the first edge = bit {bit:.1f}, symbol {bit / 5:.1f}')
        for j in range(max(0, div - 3), min(len(tr), div + 6)):
            print(f'   #{j}: meas {(tr[j][0] - tr[j - 1][0]) * 1e9 if j else 0:6.1f} ns -> {tr[j][1]:+d}'
                  f'   ideal {(tri[j][0] - tri[j - 1][0]) * 1e9 if j and j < len(tri) else 0:6.1f} ns -> '
                  f'{tri[j][1] if j < len(tri) else 0:+d}')
    # TIE over the matched part: least squares of measured vs ideal times
    k = div if div is not None else m
    if k < 3:
        print('too few matching transitions for timing analysis (different frame?)')
        k = 0
    xs = [tri[i][0] for i in range(k)]; ys = [tr[i][0] for i in range(k)]
    if not k:
        b, c, tie = 1.0, 0.0, []
    mx, my = (sum(xs) / k, sum(ys) / k) if k else (0, 0)
    if k:
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        c = my - b * mx
        tie = [(xs[i], ys[i] - (b * xs[i] + c)) for i in range(k)]
    r = math.sqrt(sum(e * e for _, e in tie) / k) if k else 0
    worst = max(tie, key=lambda p: abs(p[1])) if k else (0, 0)
    if k: print(f'TIE over {k} matched edges: rms {r * 1e9:.2f} ns, peak {worst[1] * 1e9:+.2f} ns at '
          f'{(worst[0]) * 1e6:.2f} us into the ideal; clock ratio {b:.6f}')
    # TIE by direction (DCD) and by preceding interval (DDJ)
    up = [e for (x, e), (_, s) in zip(tie, tr[:k]) if s == 1]; dn = [e for (x, e), (_, s) in zip(tie, tr[:k]) if s == -1]
    if up and dn:
        print(f'mean TIE rising {sum(up) / len(up) * 1e9:+.2f} ns, falling {sum(dn) / len(dn) * 1e9:+.2f} ns')
    after80 = [tie[i][1] for i in range(1, k) if (tri[i][0] - tri[i - 1][0]) > 60e-9]
    after40 = [tie[i][1] for i in range(1, k) if (tri[i][0] - tri[i - 1][0]) <= 60e-9]
    if after80 and after40:
        print(f'mean TIE after an 80 ns cell {sum(after80) / len(after80) * 1e9:+.2f} ns, '
              f'after 40 ns {sum(after40) / len(after40) * 1e9:+.2f} ns')
    if a.tie:
        with open(a.tie, 'w') as f:
            f.write('t_us,tie_ns\n')
            for x, e in tie:
                f.write(f'{x * 1e6:.4f},{e * 1e9:.3f}\n')
    # voltage at ideal half-cell centres (vertical eye)
    centres = []
    for i in range(1, k):
        tc = (tri[i][0] + tri[i - 1][0]) / 2  # middle between transitions in ideal time
        tmeas = b * tc + c
        j = int((tmeas - t0) / dt)
        if 0 <= j < len(seg):
            centres.append(abs(seg[j]))
    if centres:
        centres.sort()
        print(f'|v| at half-cell centres: min {centres[0]:.3f}, 1 % {centres[len(centres) // 100]:.3f}, '
              f'median {centres[len(centres) // 2]:.3f} V')
    # end of frame: last transitions and what follows
    print('last transitions (ns before the final one):',
          [round((tr[-1][0] - tr[j][0]) * 1e9, 1) for j in range(max(0, len(tr) - 8), len(tr) - 1)])
    j = int((tr[-1][0] - t0) / dt)
    tail = seg[j:j + int(1.5e-6 / dt)]
    if tail:
        print(f'after the last transition: level {tail[int(20e-9 / dt)]:+.3f} V, then min {min(tail):+.3f} max {max(tail):+.3f} V')
    if a.svg:
        # plot the last 2.5 us (measured) with the ideal underneath
        W, H = 1100, 300
        tA = tr[-1][0] - 2.0e-6; tB = tr[-1][0] + 0.6e-6
        def X(t): return 10 + (W - 20) * (t - tA) / (tB - tA)
        def Y(val): return H / 2 - val * (H / 2 - 20) / 0.8
        pts = []
        i = int((tA - t0) / dt)
        step = max(1, int(0.5e-9 / dt))
        while i < len(seg) and t0 + i * dt < tB:
            pts.append(f'{X(t0 + i * dt):.1f},{Y(seg[i]):.1f}'); i += step
        ideal_pts = []
        for ti in range(len(iv_ideal)):
            t = b * (ti / a.ideal_rate) + c
            if tA <= t <= tB:
                ideal_pts.append(f'{X(t):.1f},{Y(iv_ideal[ti]):.1f}')
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="system-ui,sans-serif" font-size="11">',
               f'<rect width="{W}" height="{H}" fill="#fcfcfb"/>']
        for lv in (0.18, -0.18, 0.0):
            svg.append(f'<line x1="10" x2="{W - 10}" y1="{Y(lv):.1f}" y2="{Y(lv):.1f}" stroke="#e1e0d9"/>')
        svg.append(f'<polyline points="{" ".join(ideal_pts)}" fill="none" stroke="#eb6834" stroke-width="1.5"/>')
        svg.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#2a78d6" stroke-width="1.5"/>')
        svg.append(f'<text x="14" y="16" fill="#0b0b0b">last 2 us of the frame at the probe (blue) and as generated (orange); grid at 0 and +/-180 mV</text>')
        svg.append('</svg>')
        open(a.svg, 'w').write('\n'.join(svg))


if __name__ == '__main__':
    main()
