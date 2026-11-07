#!/usr/bin/env python3
"""Dot plot of arb/sqi_experiments.csv: one row per impairment, the reported SQI
(or "no update") on the x axis and the symbol-error share printed beside it.
Hand-written SVG, no plotting library on the bench.

usage: sqi_plot_experiments.py [-i arb/sqi_experiments.csv] [-o arb/sqi_experiments.svg]
"""
import argparse
import csv

INK, INK2, MUTED, GRID, AXIS, SURF = '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7', '#fcfcfb'
BLUE = '#2a78d6'
FONT = 'font-family="system-ui,-apple-system,Segoe UI,sans-serif"'
GROUPS = [('amplitude', 'amp'), ('edge time', 'edge'), ('low-pass', 'lp'), ('ringing', 'ring'),
          ('DC offset', 'off'), ('noise', 'noise'), ('tone', 'tone'), ('duty-cycle distortion', 'dcd'),
          ('periodic jitter', 'pj'), ('data-dependent jitter', 'ddj'), ('uniform jitter', 'uni'),
          ('combinations', None)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-i', default='arb/sqi_experiments.csv')
    ap.add_argument('-o', default='arb/sqi_experiments.svg')
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(a.i)) if r['sqi'] != 'fail']

    def group(spec):
        for name, pre in GROUPS:
            if pre and spec.startswith(pre) and '_j' not in spec and spec not in ('edge30_j2', 'amp0.6_j3', 'lp15_j2'):
                return name
        return 'combinations'
    ordered = []
    for name, _ in GROUPS:
        ordered.append((name, [r for r in rows if group(r['spec']) == name]))

    L, R, W = 230, 130, 720
    rowh, top = 15, 70
    nrows = sum(len(rs) + 1 for _, rs in ordered)
    H = top + rowh * nrows + 40
    def X(q): return L + (W - L - R) * q / 8          # columns 0..7 and "none" at 8
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" {FONT} font-size="12">',
         f'<rect width="{W}" height="{H}" fill="{SURF}"/>',
         f'<text x="{L}" y="22" font-size="15" font-weight="600" fill="{INK}">LAN8650 SQI for single analog and timing impairments</text>',
         f'<text x="{L}" y="36" fill="{INK2}" font-size="11">120-byte frames, 1 Vpp unless stated, 250 MSa/s, 2026-11-03 cable; right column: symbol errors</text>']
    for q in range(9):
        x = X(q)
        o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top - 6}" y2="{H - 34}" stroke="{GRID}"/>')
        o.append(f'<text x="{x:.1f}" y="{top - 10}" text-anchor="middle" fill="{MUTED}">{"none" if q == 8 else q}</text>')
    o.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 10}" text-anchor="middle" fill="{INK2}">reported SQI (none: no valid measurement within 36k frames)</text>')
    o.append(f'<text x="{W - R + 34}" y="{top - 10}" fill="{MUTED}">errors</text>')
    y = top
    for name, rs in ordered:
        o.append(f'<text x="{L - 8}" y="{y + 11}" text-anchor="end" font-weight="600" fill="{INK}">{name}</text>')
        y += rowh
        for r in rs:
            q = 8 if r['sqi'] == '' else int(r['sqi'])
            f, e = int(r['frames'] or 0), int(r['symbol_errors'] or 0)
            pct = 100 * e / (f + e) if f + e else 0
            o.append(f'<line x1="{L}" x2="{W - R}" y1="{y + 7}" y2="{y + 7}" stroke="{GRID}"/>')
            o.append(f'<text x="{L - 8}" y="{y + 11}" text-anchor="end" fill="{INK2}">{r["spec"]}</text>')
            fill = SURF if q == 8 else BLUE
            o.append(f'<circle cx="{X(q):.1f}" cy="{y + 7}" r="5" fill="{fill}" stroke="{BLUE}" stroke-width="2"/>')
            lab = f'{pct:.0f} %' if pct >= 0.5 else (f'{e}' if e else '0')
            o.append(f'<text x="{W - R + 34}" y="{y + 11}" fill="{INK2}">{lab}</text>')
            y += rowh
    o.append('</svg>')
    open(a.o, 'w').write('\n'.join(o))
    print(f'{a.o}: {len(rows)} rows')


if __name__ == '__main__':
    main()
