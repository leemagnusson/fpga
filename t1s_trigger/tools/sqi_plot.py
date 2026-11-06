#!/usr/bin/env python3
"""Draw arb/sqi_sweep.csv as an SVG: reported SQI against the rms edge jitter of
the injected waveform, plus the symbol-error rate, with the empirical fit.
No plotting library on the bench, so the SVG is written by hand.

usage: sqi_plot.py [-i arb/sqi_sweep.csv] [-o arb/sqi_sweep.svg] [-a 0.5]
"""
import argparse
import csv
import math

INK, INK2, MUTED, GRID, AXIS, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
BLUE, ORANGE = '#2a78d6', '#eb6834'
FONT = 'font-family="system-ui,-apple-system,Segoe UI,sans-serif"'


def fit(points):
    """Least squares of (sqi + 0.5) against log2(jitter), SQI 0 excluded (saturated)."""
    xs = [math.log2(s) for s, q in points if q > 0]
    ys = [q + 0.5 for s, q in points if q > 0]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, b


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-i', default='arb/sqi_sweep.csv')
    ap.add_argument('-o', default='arb/sqi_sweep.svg')
    ap.add_argument('-a', type=float, default=0.5, help='amplitude (t1s_arb -a) to plot')
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(a.i)) if float(r['amplitude']) == a.a and r['sqi'] != 'fail']
    meas = [(float(r['jitter_ns']), int(r['sqi']), int(r['frames']), int(r['symbol_errors']))
            for r in rows if r['sqi'] != '']
    none = [(float(r['jitter_ns']), int(r['frames'])) for r in rows if r['sqi'] == '' and float(r['jitter_ns']) > 0]
    meas = [m for m in meas if m[0] > 0]
    c0, c1 = fit([(s, q) for s, q, _, _ in meas])

    W, H = 720, 520
    L, R = 70, 30
    top = dict(y0=40, y1=300)          # SQI panel
    bot = dict(y0=340, y1=470)         # error-rate panel
    xmin, xmax = 0.5, 12.0
    def X(s): return L + (W - L - R) * (math.log2(s) - math.log2(xmin)) / (math.log2(xmax) - math.log2(xmin))
    def Ytop(q): return top['y1'] - (top['y1'] - top['y0']) * (q + 0.5) / 9      # rows 0..7 + "none" at 8
    def Ybot(p): return bot['y1'] - (bot['y1'] - bot['y0']) * min(p, 100) / 100

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" {FONT} font-size="12">',
         f'<rect width="{W}" height="{H}" fill="{SURF}"/>',
         f'<text x="{L}" y="22" font-size="15" font-weight="600" fill="{INK}">LAN8650 SQI against injected edge jitter</text>',
         f'<text x="{L}" y="36" fill="{INK2}" font-size="11">120-byte frames, {a.a * 2:g} Vpp, 250 MSa/s, Gaussian jitter on every edge; one measurement per point, 2026-11-03 cable</text>']
    # gridlines and y labels, top
    for q in range(9):
        y = Ytop(q)
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}">{"no update" if q == 8 else q}</text>')
    for p in (0, 25, 50, 75, 100):
        y = Ybot(p)
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}">{p}%</text>')
    # x ticks (both panels)
    for s in (0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8, 12):
        x = X(s)
        for pan in (top, bot):
            o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pan["y1"]}" y2="{pan["y1"] + 4}" stroke="{AXIS}"/>')
        o.append(f'<text x="{x:.1f}" y="{bot["y1"] + 16}" text-anchor="middle" fill="{MUTED}">{s:g}</text>')
    o.append(f'<text x="{(L + W - R) / 2:.0f}" y="{bot["y1"] + 32}" text-anchor="middle" fill="{INK2}">rms edge jitter, ns (log scale)</text>')
    o.append(f'<text transform="translate(16,{(top["y0"] + top["y1"]) / 2:.0f}) rotate(-90)" text-anchor="middle" fill="{INK2}">reported SQI</text>')
    o.append(f'<text transform="translate(16,{(bot["y0"] + bot["y1"]) / 2:.0f}) rotate(-90)" text-anchor="middle" fill="{INK2}">symbol errors</text>')
    for pan in (top, bot):
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{pan["y1"]}" y2="{pan["y1"]}" stroke="{AXIS}"/>')
    # fitted step curve: floor(c0 + c1*log2(s)) clipped to 0..7, drawn as the step function
    path = []
    s = xmin
    while s <= xmax:
        q = max(0, min(7, math.floor(c0 + c1 * math.log2(s))))
        path.append((X(s), Ytop(q)))
        s *= 1.01
    d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in path)
    o.append(f'<path d="{d}" fill="none" stroke="{ORANGE}" stroke-width="2" stroke-linejoin="round"/>')
    # error-rate line + markers
    err = sorted((s, 100 * e / (f + e) if f + e else 0) for s, _, f, e in meas)
    d = 'M' + ' L'.join(f'{X(s):.1f},{Ybot(p):.1f}' for s, p in err)
    o.append(f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-width="2" stroke-linejoin="round"/>')
    for s, p in err:
        o.append(f'<circle cx="{X(s):.1f}" cy="{Ybot(p):.1f}" r="4" fill="{BLUE}" stroke="{SURF}" stroke-width="2"/>')
    # measured SQI points (duplicates nudged apart)
    seen = {}
    for s, q, _, _ in meas:
        k = (s, q); n = seen.get(k, 0); seen[k] = n + 1
        o.append(f'<circle cx="{X(s) + 6 * n:.1f}" cy="{Ytop(q):.1f}" r="5" fill="{BLUE}" stroke="{SURF}" stroke-width="2"/>')
    for s, f in none:
        o.append(f'<circle cx="{X(s):.1f}" cy="{Ytop(8):.1f}" r="5" fill="{SURF}" stroke="{BLUE}" stroke-width="2"/>')
    # legend
    lx, ly = W - R - 330, top["y0"] + 12
    o.append(f'<circle cx="{lx}" cy="{ly}" r="5" fill="{BLUE}" stroke="{SURF}" stroke-width="2"/>')
    o.append(f'<text x="{lx + 10}" y="{ly + 4}" fill="{INK2}">measured SQI (hollow: no update within 36k frames)</text>')
    o.append(f'<line x1="{lx - 6}" x2="{lx + 6}" y1="{ly + 18}" y2="{ly + 18}" stroke="{ORANGE}" stroke-width="2"/>')
    o.append(f'<text x="{lx + 10}" y="{ly + 22}" fill="{INK2}">fit: SQI = floor({c0:.2f} {c1:+.2f} log2(jitter / 1 ns))</text>')
    o.append('</svg>')
    open(a.o, 'w').write('\n'.join(o))
    print(f'{a.o}: {len(meas)} points, {len(none)} without update; fit sqi+0.5 = {c0:.3f} + {c1:.3f} log2(ns)')


if __name__ == '__main__':
    main()
